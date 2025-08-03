import pytest
import paramiko
import socket
import time
from unittest.mock import patch, MagicMock, call

from vm_connection.ssh_connection import SSHConnection
from vm_connection.exceptions import (
    ConnectionFailed,
    CommandTimeout,
    UnexpectedRebootDetected,
    BootTimeUnavailable
)

class FakeThread:
    def __init__(self, target, args=(), kwargs=None, should_hang=False):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}
        self._should_hang = should_hang

    def start(self):
        if not self._should_hang:
            self._target(*self._args, **self._kwargs)

    def join(self, timeout=None):
        pass

def create_thread(should_hang):
    def fake_thread_factory(target=None, args=(), kwargs=None):
        return FakeThread(target=target, args=args, kwargs=kwargs, should_hang=should_hang)
    return fake_thread_factory

@pytest.fixture
def ssh():
    return SSHConnection(host="test.com", username="user", key_path="/path/to/key")

@pytest.fixture
def mock_sshclient():
    with patch("paramiko.SSHClient") as mock:
        yield mock

@pytest.fixture
def mock_key():
    with patch("paramiko.RSAKey.from_private_key_file") as mock:
        yield mock


def test_successful_connection(ssh, mock_sshclient, mock_key):
    mock_instance = mock_sshclient.return_value
    mock_instance.connect.return_value = None
    mock_instance.get_transport.return_value = MagicMock(is_active=lambda: True)

    with patch.object(SSHConnection, "get_boot_time", return_value=time.time()):
        ssh.connect()

    assert ssh.client is not None
    assert ssh.transport.is_active()

@patch("vm_connection.ssh_connection.threading.Thread", side_effect=create_thread(should_hang=False))
def test_execute_with_output_callback(mock_thread, ssh):
    ssh.client = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    ssh.client.exec_command.return_value = (None, mock_stdout, mock_stderr)

    mock_channel = MagicMock()
    mock_channel.recv_exit_status.return_value = 0
    mock_stdout.channel = mock_channel

    callback_output = []
    def capture_callback(line):
        callback_output.append(line)

    with patch("vm_connection.ssh_connection.iter") as mock_iter:
        def line_generator():
            for line in ["line 1\n", "line 2\n", ""]:
                if line == "":
                    yield None 
                else:
                    yield line

        mock_iter.return_value = line_generator()

        exit_code = ssh.execute("echo test", timeout=5, output_callback=capture_callback)

    assert exit_code == 0
    assert callback_output == ["[stdout]: line 1", "[stdout]: line 2"]

@patch("vm_connection.ssh_connection.threading.Thread", side_effect=create_thread(should_hang=True))
def test_execute_timeout(mock_thread, ssh):
    ssh.client = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    ssh.client.exec_command.return_value = (None, mock_stdout, mock_stderr)
    mock_stdout.channel.recv_exit_status.return_value = 0

    with patch("vm_connection.ssh_connection.time") as mock_time:
        mock_time.time.side_effect = [1000, 1000.5, 1001.1]

        with pytest.raises(CommandTimeout):
            ssh.execute("sleep 60", timeout=1)

def test_reconnect_success(ssh, mock_sshclient, mock_key):
    ssh.client = MagicMock()
    ssh.transport = MagicMock(is_active=lambda: False)

    with patch.object(SSHConnection, "connect") as mock_connect:
        ssh.reconnect()
        mock_connect.assert_called_once()

def test_unexpected_reboot(ssh):
    ssh.client = MagicMock()
    ssh.boot_time = 1000000

    with patch.object(SSHConnection, "get_boot_time", return_value=1000009):
        with pytest.raises(UnexpectedRebootDetected):
            ssh.check_for_reboot()

def test_ping_host_success(ssh):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert ssh.ping_host() is True

def test_ping_host_fails(ssh):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert ssh.ping_host() is False
