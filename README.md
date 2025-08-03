# Resilient VM Connection Module

As requested by the assignment, a robust Python module for maintaining resilient connections to remote VMs.
Features:
 - Real-time command output streaming with callback function
 - Reconnection with configurable retry attempt number and a delay.
 - Unexpected reboot detection
 - Comprehensive failure diagnostics

## Installation

### Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

```python
from vm_connection import SSHConnection

# Initialize connection
conn = SSHConnection(
    host="192.168.1.100",
    username="admin",
    key_path="/path/to/ssh_key"
)
conn.connect()

# Execute command with real-time output
def log_output(line):
    print(f"[REMOTE] {line}")

exit_code = conn.execute(
    "sudo stress-ng --net 4",
    timeout=300,
    output_callback=log_output
)

# Check VM state
if conn.is_alive():
    print("VM operational")

# Reconnect after failure
try:
    conn.reconnect(retries=5)
except ConnectionFailed:
    print("Reconnection failed")

# Detect reboots
if conn.check_for_reboot():
    print("Unexpected reboot detected!")
```

## Design choices

### `is_alive()` implementation

I decided to go with two-tiered approach to verify that the VM is alive:
1. ***SSH-based check***: Fetches boot time to confirm that the OS responds to SSH by calling check_boot_time(), checking the that the VM is alive and looking for the unexpected reboots at the same time.
2. ***Ping fallback***: When SSH check fails, uses "ping" to verify that the machine is accessible on the network layer.

This makes sure the liveness check doesn't solely depend on SSH, increases confidence in the result.

### Reboot detection

 - Tracks boot timestamp at connection time
 - Compares current vs s
 ### Reboot detection

  - Tracks boot timestamp at connection time
  - Compares current vs stored boot time with 5 second tolerance

### Testing strategy

Key things I tested:

1. SSH Connection
2. Command timeout
3. Reboot detection
4. Ping fallback behavior
5. Command output streaming
6. Reconnection

Run tests:
```bash
pytest
# or
pytest tests/
```

### Handling network-disruptive commands

Unfortunately I didn't have the time to implement the full solution. This was a new challange for me and I learned a lot while snooping around the internet in the attempts to learn more about this stuff. I will now describe the strategy I would go with when implementing the solution.

There are few things I would do before executing the long-running command. First, I would save the boot time, to check for the reboot if/when the connection fails and we recover. I already have this functionality in the SSHConnection class. Next, when running the command I would redirect the command output to a file(e.g: ./long_running_cmd.sh > /tml/some.log 2>&1), so if the connection fails, after recovery I still can see how the command ran.

When running the command, I would set the timeout longer than expected, to allow for temporary disruptions. Stream the command output real-time for monitoring(which I also already do). While running the command I would implement some mechanism to continiously verify that the connection persists. This would give me greated confidence that I will detect the connection failure as soon as it appears.

After the connection fails, first I would "ping" the machine to destinguish between SSH and system/network problems. After that I would give myself several attempts to reconnect to the machine with exponential delays between them, meaning each new attempt will wait longer to try reconnecting that the previous one did.

If all the attempts are unsuccessful, I decide that the machine is not operational. If we reconnect, I would check if a reboot had appeared while we were disconnected, so that I could handle it somehow. If there was no reboot, the last step would be to check if the command has finished and if so did it finish successfuly or not. If the command failed, maybe then we could retry running it.
