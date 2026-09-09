import socket
import threading
import time
import logger
import safe_socket
import protocol
from lottery import Lottery
import signal

STORAGE_PATH = "/tmp/bets_storage.csv"
SOCKET_TIMEOUT_SECONDS = 2
SHUTDOWN_JOIN_TIMEOUT_SECONDS = 10


class Server:
    def __init__(self, server_host: str, server_port: int, agency_quorum_min: int) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.agency_quorum_min = agency_quorum_min

        self.lottery_lock = threading.Lock()
        self.condition = threading.Condition()
        self.agencies_done = 0

        self.shutting_down = False
        self.client_threads = []
        self.server_socket = None

    def handle_sigterm(self, signum, frame):
        """Signal handler for SIGTERM: flips the shutdown flag and wakes up
        any thread waiting on the quorum condition.
        """
        logger.info("shutdown", logger.LogResult.in_progress, "signal", signum)
        self.shutting_down = True
        with self.condition:
            self.condition.notify_all()
        if self.server_socket is not None:
            self.server_socket.close()

    def _handle_client(self, client_socket):
        action = "handle-client"
        message_amount = 0
        try:
            logger.info(action, logger.LogResult.in_progress)
            client_socket.settimeout(SOCKET_TIMEOUT_SECONDS)
            lottery = Lottery(STORAGE_PATH)
            agency_id = None
            timed_out_shutdown = False

            while True:
                try:
                    msg_type, payload = protocol.recv_message(client_socket)
                except socket.timeout:
                    if self.shutting_down:
                        timed_out_shutdown = True
                        break
                    continue

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

            if timed_out_shutdown:
                logger.info(action, logger.LogResult.success, "shutdown-before-done", True)
                return

            with self.condition:
                self.agencies_done += 1
                if self.agencies_done >= self.agency_quorum_min:
                    self.condition.notify_all()
                while self.agencies_done < self.agency_quorum_min and not self.shutting_down:
                    self.condition.wait()

            if self.shutting_down:
                logger.info(action, logger.LogResult.success, "shutdown-before-quorum", True)
                return

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
        finally:
            client_socket.close()

    def run(self):
        signal.signal(signal.SIGTERM, self.handle_sigterm)

        action = "accept-connection"
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.settimeout(SOCKET_TIMEOUT_SECONDS)
        self.server_socket.bind((self.server_host, self.server_port))
        self.server_socket.listen()

        try:
            while not self.shutting_down:
                try:
                    logger.info(action, logger.LogResult.in_progress)
                    client_socket, _ = self.server_socket.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                logger.info(action, logger.LogResult.success)

                client_thread = threading.Thread(
                    target=self._handle_client, args=(client_socket,)
                )
                client_thread.start()
                self.client_threads.append(client_thread)
        finally:
            start = time.time()
            for thread in self.client_threads:
                remaining = SHUTDOWN_JOIN_TIMEOUT_SECONDS - (time.time() - start)
                if remaining <= 0:
                    break
                thread.join(timeout=remaining)
            self.server_socket.close()
            logger.info("shutdown", logger.LogResult.success)