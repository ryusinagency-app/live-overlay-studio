"""RCON helper for the isolated client integration test only."""
import sys
from rcon import RconClient

with RconClient("127.0.0.1", 25595, "lms-isolated-test") as client:
    print(client.command(sys.argv[1]))
