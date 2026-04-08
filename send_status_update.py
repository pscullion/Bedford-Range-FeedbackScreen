import argparse
import socket


def send_message(host: str, port: int, message: str) -> None:
    data = message.encode("utf-8")
    with socket.create_connection((host, port), timeout=2.0) as sock:
        sock.sendall(data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Send one status update to Beds_StatusScreen.py. "
            "Examples: OFF:0, ACK:12, AUT:2:10.9,10.8,10.7"
        )
    )
    parser.add_argument("message", help="Status message payload")
    parser.add_argument("--host", default="127.0.0.1", help="Target host")
    parser.add_argument("--port", type=int, default=5001, help="Target TCP port")
    args = parser.parse_args()

    send_message(args.host, args.port, args.message)
    print(f"Sent to {args.host}:{args.port} -> {args.message}")


if __name__ == "__main__":
    main()
