import socket
import threading
import logger
import safe_socket
import protocol
from lottery import Lottery

STORAGE_PATH = "/tmp/bets_storage.csv"


class Server:
    def __init__(self, server_host: str, server_port: int, agency_quorum_min: int) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.agency_quorum_min = agency_quorum_min

        self.lottery_lock = threading.Lock()
        self.condition = threading.Condition()
        self.agencies_done = 0

    def _handle_client(self, client_socket):
        action = "handle-client"
        message_amount = 0
        try:
            logger.info(action, logger.LogResult.in_progress)
            lottery = Lottery(STORAGE_PATH)
            agency_id = None
            while True:
                msg_type, payload = protocol.recv_message(client_socket)
                message_amount += 1
                if msg_type == protocol.BATCH:
                    bets = protocol.decode_batch(payload)
                    if agency_id is None:
                        agency_id = bets[0].agency_id
                    elif agency_id != bets[0].agency_id:
                        logger.error(
                            action,
                            logger.LogResult.fail,
                            "agency-id-mismatch",
                            f"expected {agency_id}, got {bets[0].agency_id}",
                        )
                        raise ValueError(
                            f"Agency ID mismatch: expected {agency_id}, got {bets[0].agency_id}"
                        )
                    with self.lottery_lock:
                        lottery.store_bets(bets)
                    protocol.send_message(client_socket, protocol.ACK, b"")
                elif msg_type == protocol.DONE:
                    break
                else:
                    logger.error(
                        action,
                        logger.LogResult.fail,
                        "invalid-message-type",
                        f"got {msg_type}",
                    )
                    raise ValueError(f"Invalid message type: {msg_type}")

            with self.condition:
                self.agencies_done += 1
                if self.agencies_done >= self.agency_quorum_min:
                    self.condition.notify_all()
                while self.agencies_done < self.agency_quorum_min:
                    self.condition.wait()

            with self.lottery_lock:
                all_bets = lottery.load_bets()
            only_winners = [bet for bet in all_bets if (lottery.has_won(bet) and bet.agency_id == agency_id)]
            coding_winners = protocol.encode_winners(only_winners)
            protocol.send_message(client_socket, protocol.WINNERS, coding_winners)
            logger.info(action, logger.LogResult.success, "messages-amount", message_amount)
                
        except Exception as e:
            logger.error(
                action, logger.LogResult.fail, "messages-amount", message_amount
            )
            raise e

    def run(self):
        action = "accept-connection"
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
            server_socket.bind((self.server_host, self.server_port))
            server_socket.listen()
            while True:
                try:
                    logger.info(action, logger.LogResult.in_progress)
                    client_socket, _ = server_socket.accept()
                except Exception as e:
                    logger.error(action, logger.LogResult.fail)
                    raise e
                logger.info(action, logger.LogResult.success)

                client_thread = threading.Thread(
                    target=self._handle_client, args=(client_socket,)
                )
                client_thread.start()
