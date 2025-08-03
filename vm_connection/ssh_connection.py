import paramiko
import socket
import time
import threading
import queue
import logging
import subprocess
import platform

from vm_connection.exceptions import (
    ConnectionFailed,
    CommandTimeout,
    UnexpectedRebootDetected,
    BootTimeUnavailable
)

class SSHConnection:
    def __init__(self, host: str, username: str, key_path: str, port: int = 22, timeout: int = 10):
        self.host = host
        self.username = username
        self.key_path = key_path
        self.port = port
        self.timeout = timeout
        self.client = None
        self.transport = None
        self.boot_time = None

    def connect(self):
        try:
            key = paramiko.RSAKey.from_private_key_file(self.key_path)
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname = self.host,
                port = self.port,
                username = self.username,
                pkey = key,
                timeout = self.timeout
            )
            self.transport = self.client.get_transport()
            self.boot_time = self.get_boot_time()
        except (paramiko.SSHException, socket.error) as e:
            raise ConnectionFailed(f"Failed to connect to {self.host}: {e}")

    def execute(self, command: str, timeout: int = 60, output_callback=None) -> int:
        if not self.client:
            raise ConnectionFailed("SSH Connection is not established.")

        stdin, stdout, stderr = self.client.exec_command(command)

        output_queue = queue.Queue()
        print(f"Queue object: {output_queue.empty()}")
        print(f"Stream object: {stdout}")

        def stream_reader(stream, stream_name):
            for line in iter(stream.readline(), ''):
                output_queue.put((stream_name, line))
            output_queue.put((stream_name, None))

        stdout_thread = threading.Thread(target=stream_reader, args=(stdout, "stdout"))
        stderr_thread = threading.Thread(target=stream_reader, args=(stderr, "stderr"))
        stdout_thread.start()
        stderr_thread.start()
        print(f"Queue object: {output_queue.empty()}")

        start_time = time.time()
        print(f"Start time is {start_time}")
        stdout_done = stderr_done = False

        try:
            while not (stdout_done and stderr_done):
                try:
                    stream_name, line = output_queue.get(timeout=1)
                    print(f"Queue line: {line}")
                except queue.Empty:
                    print(f"Queue empty, time is {time.time()}")
                    if time.time() - start_time >= timeout:
                        raise CommandTimeout(f"Command {command} timed out after {timeout} seconds.")
                    continue

                if line is None:
                    if stream_name == "stdout":
                        stdout_done = True
                    if stream_name == "stderr":
                        stderr_done = True
                    continue

                if output_callback:
                    output_callback(f"[{stream_name}]: {line.strip()}")
        finally:
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)

        print(f"Exit status: {stdout.channel.recv_exit_status()}")
        return stdout.channel.recv_exit_status()

    def is_alive(self) -> bool:
        try:
            boot_time = self.get_boot_time()
            self.check_for_reboot(boot_time)

            return True

        except Exception as e:
            logging.warning(f"SSH boot time check failed: {e}")

        if self.ping_host():
            logging.info("Ping successful, but SSH failed.")
            return True

        raise ConnectionFailed("Machine is not reachable via SSH or ping.")

    def check_for_reboot(self, boot_time: float):
        if self.boot_time and abs(boot_time - self.boot_time) > 5:
            self.boot_time = boot_time
            raise UnexpectedRebootDetected("Detected unexpected reboot.")

        if self.boot_time is None:
            self.boot_time = boot_time

    def ping_host(self, count: int = 1, timeout: int = 2) -> bool:
        try:
            result = subprocess.run(
                ["ping", "-c", str(count), "-W", str(timeout), self.host],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            return result.returncode == 0
        except Exception:
            logging.warning("Pinging the machine failed.")
            return False

    def reconnect(self, force: bool = False, retries: int = 3, delay: int = 2):
        if not force and self.client:
            if self.transport and self.transport.is_active():
                logging.info("SSH connection is active. Will not reconnect.")
                return

        if self.client:
            logging.info("Closing existing SSH connection.")
            self.client.close()
            self.client = None

        for attempt in range(retries):
            try:
                logging.info(f"Reconnect attempt #{attempt+1} of {retries}")
                self.connect()
                logging.info("Reconnection successful.")
                return
            except Exception as e:
                logging.warning(f"Reconnect attempt #{attempt+1} failed: {e}")
                time.sleep(delay)

        raise ConnectionFailed(f"Failed to reconnect after {retries} attempts.")


    def get_boot_time(self) -> float:
        output_lines = []

        def collect_output(line):
            output_lines.append(line)

        try:
            self.execute("cut -f1 -d. /proc/uptime", timeout=5, output_callback=collect_output)
            if not output_lines:
                raise BootTimeUnavailable("No output recieved for uptime")

            uptime_str = output_lines[0].strip()
            uptime_seconds = float(uptime_str)
            return time.time() - uptime_seconds
        except (ValueError, CommandTimeout):
            raise BootTimeUnavailable(f"Failed to determine boot time: {e}")

    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
            self.transport = None

