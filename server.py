import argparse
import socket
import threading
import time


# ------------------- Server Logic ------------------- #

def handle_client(conn: socket.socket, addr, config):
    print(f"[server] connected to {addr}")

    max_msg_size = config["maximum_message_size"]
    dynamic = config["dynamic_message_size"]

    segments = {}
    highest_seq = -1
    received_fin = False

    with conn:
        buffer = b""

        while True:
            data = conn.recv(4096)
            if not data:
                break

            buffer += data

            while b"\n" in buffer:
                line, _, buffer = buffer.partition(b"\n")

                if not line:
                    continue

                # ---------- Handshake ----------
                if line == b"SIN":
                    conn.sendall(b"SIN/ACK\n")

                elif line == b"ACK":
                    continue

                # ---------- Max Message Size ----------
                elif line == b"GetMaxMsgSize":
                    resp = f"MaxMsgSize:{max_msg_size}\n".encode()
                    conn.sendall(resp)
                    print(f"[server] sent MaxMsgSize {max_msg_size}")

                # ---------- FIN ----------
                elif line == b"FIN":
                    received_fin = True
                    print("[server] FIN received")

                # ---------- Data Segment ----------
                elif line.startswith(b"M"):
                    try:
                        header, payload = line[1:].split(b":", 1)
                        seq = int(header)

                        segments[seq] = payload
                        print(f"[server] received segment {seq} ({len(payload)} bytes)")

                        while highest_seq + 1 in segments:
                            highest_seq += 1

                        # Dynamic max message size
                        ack = f"ACK:{highest_seq}"
                        if dynamic:
                            max_msg_size = max(4, max_msg_size - 1)
                            ack += f":MAX:{max_msg_size}"
                        
                        if not received_fin:
                            conn.sendall((ack + "\n").encode())
                            
                    except ValueError:
                        print(f"[server] Error parsing line: {line}")
                    except OSError:
                        print("[server] client closed connection, stopping ACKs")
                        return


                # ---------- Completion ----------
                if received_fin and highest_seq + 1 == len(segments):
                    full_message = b"".join(segments[i] for i in range(len(segments)))
                    print("\n[server] COMPLETE MESSAGE RECEIVED:")
                    try:
                        print(full_message.decode("utf-8"))
                    except UnicodeDecodeError:
                        print(full_message)
                    print("[server] end of message\n")
                    return


# ------------------- Config Parsing ------------------- #

def read_config(f):
    config = {}
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        key, value = line.split(":", 1)

        key = key.strip().lower().replace(" ", "_").replace("\ufeff", "")
        value = value.strip()

        if key == "dynamic_message_size":
            config[key] = value.lower() == "true"
        elif value.isdigit():
            config[key] = int(value)

    return config



# ------------------- Server Setup ------------------- #

def serve(host, port, config):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(5)

        print(f"[server] listening on {host}:{port}")

        while True:
            conn, addr = s.accept()
            threading.Thread(
                target=handle_client,
                args=(conn, addr, config),
                daemon=True
            ).start()


# ------------------- Main ------------------- #

def main():
    ap = argparse.ArgumentParser(description="Reliable TCP Server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--config", type=str)

    args = ap.parse_args()

    if args.config:
        with open(args.config, "r") as f:
            config = read_config(f)
    else:
        config = {
            "maximum_message_size": int(input("Max message size (bytes): ").strip()),
            "dynamic_message_size": input("Dynamic message size? (y/n): ").lower() == "y"
        }
    print("SERVER CONFIG:", config)

    serve(args.host, args.port, config)


if __name__ == "__main__":
    main()