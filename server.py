import argparse
import json
import socket
import threading

max_msg_size = 10

def getMaxMsgSize() -> int:
    return 10  # Example fixed size

def serve(host: str, port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, port))
        s.listen(16)
        print(f"[server] listening on {host}:{port}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

def handle_client(conn: socket.socket, addr):
    segments = {}
    highest_seq = -1
    with conn:
        try:
            buff = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break

                buff += chunk
                while b"\n" in buff:
                    line, _, buff = buff.partition(b"\n")
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith(b"SIN"):
                        # Handle SIN handshake
                        print("[server] received SIN from", addr)
                        print("[server] sending SIN/ACK to", addr)
                        conn.sendall(b"SIN/ACK\n")
                    elif line.startswith(b"GetMaxMsgSize"):
                        # Handle GetMaxMsgSize request
                        max_msg_size = getMaxMsgSize()  # Example fixed size
                        resp = "MaxMsgSize: " + str(max_msg_size)
                        print(f"[server] sending MaxMsgSize {max_msg_size} to", addr)
                        conn.sendall(resp.encode("utf-8") + b"\n")
                    elif line.startswith(b"M"):
                        # Handle message segments
                        seq_num_str, segment_data = line[1:].split(b":", 1)
                        seq_num = int(seq_num_str)
                        segments[seq_num] = segment_data.decode("utf-8")
                        print(f"Received segment: {segment_data} (seq: {seq_num})")
                        while highest_seq + 1 in segments:
                            highest_seq += 1
                        print(f"sending ACK: {highest_seq}")
                        conn.sendall(f"ACK:{highest_seq}\n".encode("utf-8"))
                        
                        


        except Exception as e:
            try:
                err = {"ok": False, "error": f"Server exception: {e}"}
                conn.sendall((json.dumps(err, ensure_ascii=False) + "\n").encode("utf-8"))
            except Exception:
                pass

def readFile(f) -> dict:
    content = f.read()
    return json.loads(content)

def main():
    ap = argparse.ArgumentParser(description="JSON TCP server (calc/gpt) — student skeleton")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--config", type=str, default=None, help="Path to config file (if not given, runs in interactive mode)")
    args = ap.parse_args()
    if args.config is None:
        print("No config file provided. Running in interactive mode.")
        max_msg_size = int(input("Enter max message size in bytes: ").strip())
    else:
        try:
            with open(args.config, "r", encoding="utf-8") as f:
                config = readFile(f)
                max_msg_size = config.get("max_message_size", 10)
        except Exception as e:
            print(f"Error reading config file: {e}")
            return
        
    serve(args.host, args.port)

if __name__ == "__main__":
    main()