import argparse
import socket
import sys
import time


# ------------------- Client Logic ------------------- #

def handle_client(host, port, config):
    message_path = config["message"]
    initial_msg_size = config["maximum_message_size"]
    window_size = config["window_size"]
    timeout = config["timeout"]          # seconds
    dynamic = config["dynamic_message_size"]

    with open(message_path, "rb") as f:
        content = f.read()
        message_bytes = content.replace(b"\r\n", b" ").replace(b"\n", b" ")


    with socket.create_connection((host, port)) as s:
        s.settimeout(timeout)

        # ---------- Handshake ----------
        Hand_shake(s)

        # ---------- Get max message size ----------
        max_msg_size = send_max_msg_size_request(s, initial_msg_size, dynamic)

        print(f"[Client] Initial max message size = {max_msg_size} bytes")

        # ---------- Segmentation ----------
        segments = segment_bytes(message_bytes, max_msg_size)

        base = 0
        next_seq = 0
        last_ack = -1
        timer_start = None
        
        dupAckCount = 0
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

            # Wait for ACKs
            try:
                s.settimeout(timeout)
                resp = s.recv(4096)

                for line in resp.split(b"\n"):
                    if not line.startswith(b"ACK:"):
                        continue

                    parts = line.decode().split(":")
                    global_ack = int(parts[1])
                    
                    ack_num = global_ack

                    # Duplicate ACK logic
                    if ack_num == last_ack:
                        dupAckCount += 1
                        print(f"[Client] Received duplicate ACK {ack_num} (count={dupAckCount})")
                        if dupAckCount == 3:
                            print(f"[Client] Triple duplicate ACKs for {ack_num} -> fast retransmit")
                            next_seq = base
                            if dynamic:
                                max_msg_size = send_max_msg_size_request(s, int((max_msg_size+initial_msg_size)/2), dynamic)
                                segments = resegment_after_window(
                                    segments,
                                    base=base,
                                    window_size=window_size,
                                    new_max=max_msg_size
                                )
                                print(f"[Client] New max_msg_size = {max_msg_size} -> re-segmented remaining data")
                            dupAckCount = 0
                            timer_start = time.time()
                    
                    # new ACK logic
                    elif ack_num > last_ack:
                        dupAckCount = 0
                        last_ack = max(last_ack, ack_num)
                        print(f"[Client] Received ACK {global_ack}")

                        # Dynamic max message size logic
                        if dynamic and len(parts) == 4 and parts[2] == "MAX":
                            new_max = int(parts[3])
                            max_msg_size = new_max
                            segments = resegment_after_window(
                                segments,
                                base=base,
                                window_size=window_size,
                                new_max=max_msg_size
                            )
                            next_seq = max(base, next_seq)
                            print(f"[Client] New max_msg_size = {new_max} -> re-segmented remaining data")
                    base = last_ack + 1
                    if base == next_seq:
                        timer_start = None
                    else:
                        timer_start = time.time()

            except socket.timeout:
                print("[Client] Timeout -> retransmitting window")
                if dynamic:
                    max_msg_size = send_max_msg_size_request(s, initial_msg_size, dynamic)
                    segments = resegment_after_window(
                        segments,
                        base=base,
                        window_size=window_size,
                        new_max=max_msg_size
                    )
                    print(f"[Client] New max_msg_size = {max_msg_size} -> re-segmented remaining data")
                next_seq = base
                dupAckCount = 0
                timer_start = time.time()

        # ---------- End of transmission ----------
        s.sendall(b"FIN\n")
        while True:
            try:
                s.settimeout(timeout)
                resp = s.recv(1024)
                if resp.startswith(b"ACK:"):
                    print("[Client] FIN acknowledged by server")
                    s.close()
                    print("[Client] Connection closed") 
                    break
            except socket.timeout:
                s.sendall(b"FIN\n")
        print("[Client] Transmission complete")

# ------------------- Server requests ------------------- #


def Hand_shake(s):
    """Performs a three-way handshake with the server."""
    while True:
        s.sendall(b"SIN\n")
        try:
            if b"SIN/ACK" in s.recv(1024):
                s.sendall(b"ACK\n")
                break
        except socket.timeout:
            s.sendall(b"SIN\n")

def send_max_msg_size_request(s, max_msg_size, dynamic)->int:
    """Sends a GetMaxMsgSize request to the server and returns the max message size."""
    while True:
            s.sendall(f"GetMaxMsgSize:{max_msg_size},{dynamic}\n".encode())
            try:
                resp = s.recv(1024)
                if resp.startswith(b"MaxMsgSize:"):
                    max_msg_size = int(resp.split(b":")[1])
                    return max_msg_size
            except socket.timeout:
                s.sendall(f"GetMaxMsgSize:{max_msg_size},{dynamic}\n".encode())


# ------------------- Utilities ------------------- #

def segment_bytes(data: bytes, max_size: int):
    return [data[i:i+max_size] for i in range(0, len(data), max_size)]

def resegment_after_window(
    segments: list[bytes],
    *,
    base: int,
    window_size: int,
    new_max: int
) -> list[bytes]:
    """
    Re-segments ONLY the data after the current window using new_max.
    Everything before and inside the window remains unchanged.
    """

    window_end = min(base + window_size, len(segments))

    # חלקים שלא נוגעים בהם
    before = segments[:window_end]

    # כל הדאטה שאחרי החלון
    after_data = b"".join(segments[window_end:])

    # פירוק מחדש של מה שאחרי החלון
    after_segments = [
        after_data[i:i + new_max]
        for i in range(0, len(after_data), new_max)
    ]

    return before + after_segments

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
        "maximum_msg_size": int(input("Maximum message size (bytes): ").strip()),
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