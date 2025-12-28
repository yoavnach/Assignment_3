import argparse
import random
import socket
import threading
import time

lossProbability = 0.1  # probability of dropping a packet

# ------------------- Server Logic ------------------- #

def handle_client(conn: socket.socket, addr):
    print(f"[server] connected to {addr}")

    max_msg_size = 1  # Default max message size
    dynamic = False  # Default dynamic behavior

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

                if random.random() < lossProbability:
                    print("[server] Simulating packet loss")
                    print("[server] Dropped line:", line)
                    continue
                # ---------- Handshake ----------
                if line == b"SIN":
                    conn.sendall(b"SIN/ACK\n")

                elif line == b"ACK":
                    continue

                # ---------- Max Message Size ----------
                elif line.startswith(b"GetMaxMsgSize"):
                    rest = line.split(b":", 1)[1]
                    req_b, dyn_b = rest.split(b",", 1)
                    max_msg_size = int(req_b)
                    dynamic = dyn_b == b"True"
                    resp = f"MaxMsgSize:{max_msg_size}\n".encode()
                    conn.sendall(resp)
                    print(f"[server] sent MaxMsgSize {max_msg_size}")

                # ---------- FIN ----------
                elif line == b"FIN":
                    received_fin = True
                    print("[server] FIN received")
                    conn.sendall(b"ACK:\n")

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
                            max_msg_size = max_msg_size+1
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




# ------------------- Server Setup ------------------- #

def serve(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(5)

        print(f"[server] listening on {host}:{port}")

        while True:
            conn, addr = s.accept()
            threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True
            ).start()


# ------------------- Main ------------------- #

def main():
    ap = argparse.ArgumentParser(description="Reliable TCP Server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)

    args = ap.parse_args()


    serve(args.host, args.port)


if __name__ == "__main__":
    main()