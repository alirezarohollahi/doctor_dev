
import socket
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 9000

message = "hello from tcp_sender"

with socket.create_connection((HOST, PORT), timeout=5) as sock:
    print(f"Connected to {HOST}:{PORT}")

    for i in range(1, 6):
        payload = f"{message} #{i}"
        print(f"[SEND] {payload}")
        sock.sendall(payload.encode("utf-8"))

        data = sock.recv(4096)
        print(f"[REPLY] {data.decode('utf-8', errors='replace')}")

        time.sleep(1)




