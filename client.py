import argparse
import socket
import sys
import time


# ------------------- Client Logic ------------------- #

def handle_client(host, port, config):
    message_path = config["message"]
    window_size = config["window_size"]
    timeout = config["timeout"]          # seconds
    dynamic = config["dynamic_message_size"]

    with open(message_path, "rb") as f:
        message_bytes = f.read()

    with socket.create_connection((host, port)) as s:
        s.settimeout(timeout)

        # ---------- Handshake ----------
        while True:
            s.sendall(b"SIN\n")
            try:
                if b"SIN/ACK" in s.recv(1024):
                    s.sendall(b"ACK\n")
                    break
            except socket.timeout:
                continue

        # ---------- Get max message size ----------
        while True:
            s.sendall(b"GetMaxMsgSize\n")
            try:
                resp = s.recv(1024)
                if resp.startswith(b"MaxMsgSize:"):
                    max_msg_size = int(resp.split(b":")[1])
                    break
            except socket.timeout:
                continue

        print(f"[Client] Initial max message size = {max_msg_size} bytes")

        # ---------- Segmentation ----------
        segments = segment_bytes(message_bytes, max_msg_size)

        base = 0
        next_seq = 0
        last_ack = -1
        timer_start = None

        while base < len(segments):

            # Send window
            while next_seq < len(segments) and next_seq - base < window_size:
                payload = segments[next_seq]
                header = f"M{next_seq}:".encode()
                s.sendall(header + payload + b"\n")
                print(f"[Client] Sent segment {next_seq}")
                if base == next_seq:
                    timer_start = time.time()
                next_seq += 1

            try:
                s.settimeout(timeout)
                resp = s.recv(4096)

                for line in resp.split(b"\n"):
                    if not line.startswith(b"ACK:"):
                        continue

                    parts = line.decode().split(":")
                    ack_num = int(parts[1])
                    last_ack = max(last_ack, ack_num)
                    print(f"[Client] Received ACK {ack_num}")

                    # Dynamic max message size
                    if dynamic and len(parts) == 4 and parts[2] == "MAX":
                        new_max = int(parts[3])
                        if new_max != max_msg_size:
                            print(f"[Client] New max_msg_size = {new_max}")
                            max_msg_size = new_max
                            remaining = b"".join(segments[last_ack+1:])
                            segments = segment_bytes(remaining, max_msg_size)
                            base = 0
                            next_seq = 0
                            last_ack = -1
                            timer_start = None
                            break

                    base = last_ack + 1
                    if base == next_seq:
                        timer_start = None
                    else:
                        timer_start = time.time()

            except socket.timeout:
                print("[Client] Timeout -> retransmitting window")
                next_seq = base
                timer_start = time.time()

        # ---------- End of transmission ----------
        s.sendall(b"FIN\n")
        print("[Client] Transmission complete")


# ------------------- Utilities ------------------- #

def segment_bytes(data: bytes, max_size: int):
    return [data[i:i+max_size] for i in range(0, len(data), max_size)]


def readFile(f):
    config = {}
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        value = value.strip()

        if key == "dynamic_message_size":
            config[key] = value.lower() == "true"
        elif key == "message":
            config[key] = value.strip('"')
        elif value.isdigit():
            config[key] = int(value)

    return config


def interactive_config(host, port):
    config = {
        "message": input("Message file path: ").strip(),
        "window_size": int(input("Window size: ").strip()),
        "timeout": int(input("Timeout (seconds): ").strip()),
        "dynamic_message_size": input("Dynamic message size? (y/n): ").lower() == "y"
    }
    handle_client(host, port, config)


# ------------------- Main ------------------- #

def main():
    ap = argparse.ArgumentParser(description="Reliable client over TCP")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--config", type=str)

    args = ap.parse_args()

    if args.config:
        with open(args.config, "r") as f:
            config = readFile(f)
    else:
        return interactive_config(args.host, args.port)

    handle_client(args.host, args.port, config)


if __name__ == "__main__":
    main()
