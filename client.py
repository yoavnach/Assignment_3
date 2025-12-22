import argparse, socket, sys
import time






    
# ------------------- מצב אינטראקטיבי ------------------- #
def handle_client(host, port,config):
    
    message = config.get("message", "message.txt")
    timeOut = config.get("time_out", 500)  # milliseconds
    windowZise = config.get("window_size", 4)
    dynamic = config.get("dynamic_window", False)

    with socket.create_connection((host, port)) as s:
        s.sendall(b"SIN\n")
        s.settimeout(timeOut / 1000)
        while True:
            try:
                buff = s.recv(4096)
                if b"SIN/ACK" in buff:
                    s.sendall(b"ACK\n")
                    break
            except socket.timeout:
                s.sendall(b"SIN\n")
        
        s.sendall(b"GetMaxMsgSize\n")
        while True:
            try:
                buff = s.recv(4096)
                if b"MaxMsgSize" in buff:
                    max_msg_size = int(buff.split(b":")[1].strip())
                    break
            except socket.timeout:
                s.sendall(b"GetMaxMsgSize\n")

        print(f"Max message size from server: {max_msg_size} bytes")

        with open(message, "r", encoding="utf-8") as f:
            content = f.read()
            segments = segment_message(content, max_msg_size)

        base = 0
        seq = 0
        acked = -1

        while base < len(segments):
            while seq - base < windowZise and seq < len(segments):
                msg = "M"+str(seq)+":"+segments[seq]
                print(f"Sending segment {seq}: "+str(segments[seq]))
                s.sendall(msg.encode("utf-8") + b"\n")
                seq += 1

            try:
                buff = s.recv(4096)
                for line in buff.split(b"\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith(b"ACK:"):
                        print("Received " + line.decode("utf-8"))
                        print(f"current window {base} to {seq - 1}")
                        ack_num = int(line.split(b":", 1)[1].strip())
                        acked = max(acked, ack_num)
                            
            except socket.timeout:
                for i in range(base, seq):
                    msg = "M" + str(i) + ":" + segments[i]
                    print(f"Timeout -> Resending segment {i}")
                    s.sendall(msg.encode("utf-8") + b"\n")

            if dynamic:
                windowZise = min(windowZise + 1, 10)

            base = max(0, acked + 1)
        

def segment_message(message: str, max_size: int) -> list:
    segments = []
    for i in range(0, len(message), max_size):
        segments.append(message[i:i + max_size])
    return segments

def readFile(f) -> dict:
    config = {}
    for line in f:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            value = value.strip()
            # Convert to appropriate types
            if value.lower() in ('true', 'false'):
                config[key] = value.lower() == 'true'
            elif value.isdigit():
                config[key] = int(value)
            else:
                config[key] = value
    return config

def interactive_config(host: str, port: int):
    print("Entering interactive mode\n")
    message = input("Enter path to message file: ").strip()
    windowZise = int(input("Enter window size: ").strip())
    timeOut = int(input("Enter timeout (ms): ").strip())
    dynamic = input("Dynamic window size? (y/n): ").strip().lower() == 'y'

    config = {
        "message": message,
        "window_size": windowZise,
        "timeout_ms": timeOut,
        "dynamic_window": dynamic
    }

    handle_client(host, port, config)

def configure_client(host: str, port: int, requests: dict):
    handle_client(host, port, requests)

def main():
    ap = argparse.ArgumentParser(description="Client (Windowed messaging over JSON TCP)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)

    ap.add_argument("--config", type=str, default=None,
                    help="Path to JSON config file with requests (if not given, runs in interactive mode)")
    
    args = ap.parse_args()

    if args.config is None:
        interactive_config(args.host, args.port)

    else:
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                requests = readFile(f)
                configure_client(args.host, args.port, requests)
        except Exception as e:
            print(f"Error reading config file: {e}", file=sys.stderr)
            sys.exit(1)

       


if __name__ == "__main__":
    main()