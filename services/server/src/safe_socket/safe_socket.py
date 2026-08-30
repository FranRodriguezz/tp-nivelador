import socket

# recv_all reads exactly `size` bytes from socket, looping to handle
# short reads. Raises ConnectionError if the connection is closed
# before all bytes could be received.
def recv_all(sock: socket.socket, size):
    accumulated = 0
    buffer = bytearray()
    while accumulated < size:
        chunk = sock.recv(size - accumulated)
        if len(chunk) == 0:
            raise ConnectionError("Socket connection closed before receiving all bytes")
        buffer += chunk
        accumulated += len(chunk)
    return bytes(buffer)


# send_all writes all bytes to socket, looping to handle short writes.
# Raises ConnectionError if the connection is closed before all bytes
# could be sent.
def send_all(sock: socket.socket, data):
    accumulated = 0
    buffer_size = len(data)
    while accumulated < buffer_size:
        n = sock.send(data[accumulated:])
        if n == 0:
            raise ConnectionError("Socket connection closed before sending all bytes")
        accumulated += n