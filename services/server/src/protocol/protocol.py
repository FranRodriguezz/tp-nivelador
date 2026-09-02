import struct
from lottery import Bet
from safe_socket import send_all, recv_all

BET = 0
DONE = 1
WINNERS = 2

HEADER_SIZE = 3 # 1 byte tipo + 2 bytes longitud

def encode_bet(bet):
    """Encodes a Bet into bytes of its payload (without header)
    """
    bet_string = f"{bet.agency_id},{bet.first_name},{bet.last_name},{bet.document},{bet.birthdate},{bet.number}"
    return bet_string.encode("utf-8")


def decode_bet(payload):
    """Decodes a Bet from bytes of its payload (without header)
    """
    bet_string = payload.decode("utf-8")
    agency_id, first_name, last_name, document, birthdate, number = bet_string.split(",")
    return Bet(int(agency_id), first_name, last_name, int(document), birthdate, int(number))

def encode_header(msg_type, length):
    """Encodes a header with the given message type and length into bytes
    """
    return struct.pack(">BH", msg_type, length)

def decode_header(header_bytes):
    """Decodes a header from bytes into a tuple of (msg_type, length)
    """
    msg_type, length = struct.unpack(">BH", header_bytes)
    return msg_type, length

def encode_winners(winners):
    """Encodes a list of winning Bet objects into bytes containing
    their comma-separated documents (without header)
    """
    winners_string = ",".join([f"{bet.document}" for bet in winners])
    return winners_string.encode("utf-8")

def decode_winners(payload):
    """Decodes bytes of comma-separated documents into a list of ints
    """
    winners_string = payload.decode("utf-8")
    if not winners_string:
        return []
    documents = winners_string.split(",")
    return [int(document) for document in documents]

def send_message(sock, msg_type, payload):
    """Sends a message with the given type and payload over the socket
    """
    header = encode_header(msg_type, len(payload))
    send_all(sock, header + payload)

def recv_message(sock):
    """Receives a message from the socket, returning a tuple of (msg_type, payload)
    """
    header_bytes = recv_all(sock, HEADER_SIZE)
    msg_type, length = decode_header(header_bytes)
    payload = recv_all(sock, length)
    return msg_type, payload