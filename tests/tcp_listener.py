
import socket
import threading

HOST = "127.0.0.1"
PORT = 9000

def handle_client(conn, addr):
    print(f"[+] Client connected: {addr}")
    with conn:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            print(f"[RECEIVED] {text}")
            conn.sendall(f"echo from listener: {text}".encode("utf-8"))
    print(f"[-] Client disconnected: {addr}")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen()

    print(f"TCP listener running on {HOST}:{PORT}")

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()




