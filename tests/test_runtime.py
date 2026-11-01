"""Local-only Mihomo regression: set MIHOMO_BIN to enable core checks.

No live client settings, subscriptions, DNS services or internet hosts are used.
"""

import json
import os
from contextlib import contextmanager
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = os.environ.get("MIHOMO_BIN") or shutil.which("mihomo")
AI = "\U0001f916 AI"


def override(config):
    script = (ROOT / "overrides/claude-quic-reject.js").read_text(encoding="utf-8-sig")
    runner = script + "\nprocess.stdout.write(JSON.stringify(main(JSON.parse(require('fs').readFileSync(0,'utf8')))));"
    result = subprocess.run(["node", "-e", runner], input=json.dumps(config),
                            capture_output=True, text=True, encoding="utf-8", check=True,
                            timeout=10)
    return json.loads(result.stdout)


@contextmanager
def dns_server(address, queries=None):
    """A local DNS server with a fixed A answer; never contacts an upstream."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(0.05)
        stopped = threading.Event()

        def respond():
            while not stopped.is_set():
                try:
                    query, peer = server.recvfrom(4096)
                except socket.timeout:
                    continue
                if queries is not None:
                    queries.append(query)
                end = 12
                while query[end]:
                    end += query[end] + 1
                end += 5
                is_a = query[end - 4:end - 2] == b"\x00\x01"
                answer = (b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04"
                          + socket.inet_aton(address)) if is_a else b""
                response = (query[:2] + b"\x81\x80\x00\x01" +
                            (b"\x00\x01" if is_a else b"\x00\x00") +
                            b"\x00\x00\x00\x00" + query[12:end] + answer)
                server.sendto(response, peer)

        worker = threading.Thread(target=respond, daemon=True)
        worker.start()
        try:
            yield f"udp://127.0.0.1:{server.getsockname()[1]}"
        finally:
            stopped.set()
            worker.join(timeout=1)


@contextmanager
def udp_proxy():
    """SOCKS5 UDP associate endpoint; captures packets without forwarding them."""
    with socket.socket() as listener, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as relay:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(0.05)
        relay.bind(("127.0.0.1", 0))
        relay.settimeout(1)
        stopped = threading.Event()

        def respond():
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            with connection:
                connection.settimeout(1)

                def read(count):
                    data = b""
                    while len(data) < count:
                        chunk = connection.recv(count - len(data))
                        if not chunk:
                            raise EOFError("Incomplete SOCKS handshake")
                        data += chunk
                    return data

                header = read(2)
                read(header[1])
                connection.sendall(b"\x05\x00")
                header = read(4)
                size = 4 if header[3] == 1 else 16 if header[3] == 4 else read(1)[0]
                read(size + 2)
                connection.sendall(b"\x05\x00\x00\x01\x7f\x00\x00\x01" +
                                   relay.getsockname()[1].to_bytes(2, "big"))
                stopped.wait(5)

        worker = threading.Thread(target=respond, daemon=True)
        worker.start()
        try:
            yield listener.getsockname()[1], relay
        finally:
            stopped.set()
            worker.join(timeout=2)


@contextmanager
def vless_tcp_receiver():
    """Capture a VLESS request on TCP; no external server or credentials."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listener.settimeout(0.05)
        captured = bytearray()
        stopped = threading.Event()

        def receive():
            while not stopped.is_set():
                try:
                    connection, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            with connection:
                connection.settimeout(0.05)
                while not stopped.is_set():
                    try:
                        chunk = connection.recv(4096)
                    except socket.timeout:
                        continue
                    except ConnectionResetError:
                        break  # The isolated core is terminated after capture.
                    if not chunk:
                        break
                    captured.extend(chunk)

        worker = threading.Thread(target=receive, daemon=True)
        worker.start()
        try:
            yield listener.getsockname()[1], captured
        finally:
            stopped.set()
            worker.join(timeout=2)


@unittest.skipUnless(CORE, "Set MIHOMO_BIN for local-only core regression checks")
class RuntimeTests(unittest.TestCase):
    def check_udp(self, rule, host, expected_direct=False, dns=None, proxy_port=None,
                  providers=None, proxy_node=None, config_transform=override):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sink, \
                socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender, \
                tempfile.TemporaryDirectory(prefix="clash-rules-test-") as directory:
            sink.bind(("127.0.0.1", 0))
            sender.bind(("127.0.0.1", 0))
            sink.settimeout(0.12)
            # Reserve a free tunnel port separately from the destination socket.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
                reservation.bind(("127.0.0.1", 0))
                tunnel_port = reservation.getsockname()[1]
            config = config_transform({
                "mode": "rule", "log-level": "info", "ipv6": False,
                "hosts": {} if dns else {host: "127.0.0.1"},
                "dns": dns or {"enable": True, "nameserver": ["127.0.0.1"]},
                "proxies": [proxy_node or {"name": "tcp-only", "type": "socks5",
                             "server": "127.0.0.1", "port": proxy_port or 9,
                             "udp": proxy_port is not None}],
                "proxy-groups": [{"name": AI, "type": "select", "proxies": ["tcp-only"]}],
                "tunnels": [{"network": ["udp"], "address": f"127.0.0.1:{tunnel_port}",
                             "target": f"{host}:{sink.getsockname()[1]}"}],
                "rules": [rule, "MATCH,DIRECT"],
                "rule-providers": providers or {},
            })
            path = Path(directory)
            (path / "config.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            with (path / "core.log").open("w+", encoding="utf-8") as log:
                process = subprocess.Popen([CORE, "-d", directory, "-f", str(path / "config.json")],
                                           stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    deadline = time.monotonic() + 5
                    while True:
                        log.seek(0)
                        output = log.read()
                        if "tunnel" in output.lower() and "listening" in output.lower():
                            break
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail("Core did not start: " + output)
                        time.sleep(0.025)
                    received = False
                    for _ in range(3):
                        sender.sendto(b"routing-regression", ("127.0.0.1", tunnel_port))
                        try:
                            payload, _ = sink.recvfrom(1024)
                            received = payload == b"routing-regression"
                            if received:
                                break
                        except socket.timeout:
                            pass
                    log.seek(0)
                    output = log.read()
                    self.assertIn("[UDP]", output, "No packet reached the core: " + output)
                    self.assertEqual(received, expected_direct,
                                     "UDP escaped through DIRECT" if received else output)
                    if not expected_direct:
                        self.assertIn(f"{AI}[tcp-only]" if proxy_port or proxy_node else "REJECT", output)
                finally:
                    process.terminate()
                    process.wait(timeout=5)

    def test_claude_non_quic_udp_cannot_fall_through_to_direct(self):
        self.check_udp(f"DOMAIN-SUFFIX,claude.com,{AI}", "claude.com")

    def test_stun_udp_cannot_fall_through_to_direct(self):
        self.check_udp(f"DOMAIN,stun.l.google.com,{AI}", "stun.l.google.com")

    def test_literal_voice_ip_udp_cannot_fall_through_to_direct(self):
        self.check_udp(f"IP-CIDR,127.0.0.1/32,{AI},no-resolve", "127.0.0.1")

    def test_keyword_udp_cannot_fall_through_to_direct(self):
        self.check_udp(f"DOMAIN-KEYWORD,claude,{AI}", "claude.com")

    def test_other_proxy_group_udp_cannot_fall_through_to_direct(self):
        self.check_udp("DOMAIN,overseas.example,tcp-only", "overseas.example")

    def test_unmatched_udp_cannot_fall_through_to_implicit_direct(self):
        self.check_udp(f"MATCH,{AI}", "127.0.0.1")

    def test_domestic_udp_remains_direct(self):
        self.check_udp("DOMAIN-SUFFIX,wechat.com,DIRECT", "wechat.com", expected_direct=True)

    def test_udp_capable_proxy_still_receives_packets(self):
        with udp_proxy() as (port, relay):
            self.check_udp(f"DOMAIN-SUFFIX,claude.com,{AI}", "claude.com", proxy_port=port)
            packet, _ = relay.recvfrom(4096)
            self.assertTrue(packet.endswith(b"routing-regression"))

    def test_vless_carries_udp_inside_tcp_even_if_subscription_disables_udp(self):
        for encoding in (None, "xudp", "packetaddr"):
            with self.subTest(encoding=encoding), vless_tcp_receiver() as (port, captured):
                node = {"name": "tcp-only", "type": "vless", "server": "127.0.0.1",
                        "port": port, "network": "tcp", "udp": False,
                        "uuid": "00000000-0000-4000-8000-000000000001"}
                if encoding:
                    node["packet-encoding"] = encoding
                self.check_udp(f"DOMAIN-SUFFIX,claude.com,{AI}", "claude.com", proxy_node=node)
                self.assertEqual(captured[:17], b"\x00" +
                                 bytes.fromhex("00000000000040008000000000000001"))
                self.assertIn(b"routing-regression", captured)

    def test_rule_set_udp_cannot_fall_through_to_direct(self):
        self.check_udp(f"RULE-SET,protected,{AI},no-resolve", "claude.com", providers={
            "protected": {"type": "inline", "behavior": "domain", "payload": ["+.claude.com"]},
        })

    def test_direct_dns_does_not_inherit_overseas_policy(self):
        with dns_server("127.0.0.1") as domestic, dns_server("127.0.0.2") as overseas:
            self.check_udp("DOMAIN-SUFFIX,wechat.com,DIRECT", "wechat.com", expected_direct=True,
                           dns={"enable": True, "ipv6": False,
                                "nameserver": [overseas],
                                "nameserver-policy": {"wechat.com": [overseas]},
                                "direct-nameserver": [domestic],
                                "direct-nameserver-follow-policy": True})

    def test_converted_voice_pin_does_not_resolve_unrelated_domain(self):
        queries = []
        with dns_server("127.0.0.1") as domestic, dns_server("127.0.0.1", queries) as overseas:
            # The client converter has dropped no-resolve from an early AI IP pin.
            self.check_udp(f"IP-CIDR,203.0.113.8/32,{AI}", "wechat.com", expected_direct=True,
                           dns={"enable": True, "ipv6": False, "nameserver": [overseas],
                                "direct-nameserver": [domestic]})
        self.assertEqual(len(queries), 0, "An unrelated domain was resolved by an early voice IP rule")


if __name__ == "__main__":
    unittest.main()
