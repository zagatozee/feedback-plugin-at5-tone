"""
at5_midi_bridge.py - AT5 MIDI Bridge
Uses Windows winmm API directly via ctypes - no extra dependencies needed.

Usage:
    python at5_midi_bridge.py [--port 37432] [--midi-port "AXE IO"]
"""

import argparse, ctypes, ctypes.wintypes, json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

winmm = ctypes.WinDLL("winmm")
MMSYSERR_NOERROR = 0
midi_out_handle = ctypes.wintypes.HANDLE(0)
midi_port_name  = "AXE IO"


def list_outputs():
    class MIDIOUTCAPS(ctypes.Structure):
        _fields_ = [
            ("wMid",           ctypes.wintypes.WORD),
            ("wPid",           ctypes.wintypes.WORD),
            ("vDriverVersion", ctypes.wintypes.DWORD),
            ("szPname",        ctypes.c_wchar * 32),
            ("wTechnology",    ctypes.wintypes.WORD),
            ("wVoices",        ctypes.wintypes.WORD),
            ("wNotes",         ctypes.wintypes.WORD),
            ("wChannelMask",   ctypes.wintypes.WORD),
            ("dwSupport",      ctypes.wintypes.DWORD),
        ]
    count = winmm.midiOutGetNumDevs()
    devices = []
    for i in range(count):
        caps = MIDIOUTCAPS()
        winmm.midiOutGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps))
        devices.append((i, caps.szPname))
    return devices


def init_midi(port_name):
    global midi_out_handle, midi_port_name
    midi_port_name = port_name
    devices = list_outputs()
    print(f"Found {len(devices)} MIDI output device(s):")
    target_id = None
    for dev_id, name in devices:
        marker = " <- TARGET" if port_name.lower() in name.lower() else ""
        print(f"  [{dev_id}] {name}{marker}")
        if port_name.lower() in name.lower() and target_id is None:
            target_id = dev_id
    if target_id is None:
        print(f"\nERROR: Could not find output port matching '{port_name}'")
        sys.exit(1)
    handle = ctypes.wintypes.HANDLE(0)
    result = winmm.midiOutOpen(ctypes.byref(handle), target_id, 0, 0, 0)
    if result != MMSYSERR_NOERROR:
        print(f"\nERROR: midiOutOpen failed (code {result})")
        sys.exit(1)
    midi_out_handle = handle
    print(f"\nMIDI output ready -> [{target_id}] {port_name}  (handle={handle.value})")


def send_raw(dword):
    result = winmm.midiOutShortMsg(midi_out_handle, ctypes.wintypes.DWORD(dword))
    if result != MMSYSERR_NOERROR:
        # Decode common winmm error codes
        ERRORS = {
            2:  "MMSYSERR_BADDEVICEID — device ID out of range",
            5:  "MMSYSERR_INVALHANDLE — invalid handle (device disconnected?)",
            11: "MMSYSERR_INVALPARAM — invalid parameter",
            65: "MIDIERR_NOTREADY — hardware busy",
            67: "MIDIERR_BADOPENMODE — wrong open mode",
        }
        msg = ERRORS.get(result, f"winmm error code {result}")
        print(f"  midiOutShortMsg FAILED: {msg}")
        return False
    return True


def send_pc(channel, bank_msb, bank_lsb, program):
    ch = channel & 0x0F
    try:
        if bank_msb > 0: send_raw((0xB0|ch) | (0<<8)  | ((bank_msb&0x7F)<<16))
        if bank_lsb > 0: send_raw((0xB0|ch) | (32<<8) | ((bank_lsb&0x7F)<<16))
        ok = send_raw((0xC0|ch) | ((program&0x7F)<<8))
        print(f"  PC -> ch={channel} bank={bank_msb} prog={program}  (preset #{bank_msb*128+program+1})  {'OK' if ok else 'FAILED'}")
        return ok
    except Exception as e:
        print(f"  MIDI error: {e}"); return False


def send_cc(channel, cc, value):
    ch = channel & 0x0F
    try:
        ok = send_raw((0xB0|ch) | ((cc&0x7F)<<8) | ((value&0x7F)<<16))
        print(f"  CC  -> ch={channel} cc={cc} val={value}  {'OK' if ok else 'FAILED'}")
        return ok
    except Exception as e:
        print(f"  MIDI error: {e}"); return False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type",  "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/ping":
            self._json(200, {"ok": True, "midi_port": midi_port_name, "ready": True})
        elif parsed.path == "/send_cc":
            # GET /send_cc?cc=20&value=64&channel=0
            cc  = int(qs.get("cc",  ["0"])[0])
            val = int(qs.get("value", ["64"])[0])
            ch  = int(qs.get("channel", ["0"])[0])
            ok  = send_cc(ch, cc, val)
            self._json(200 if ok else 500, {"ok": ok, "cc": cc, "value": val})
        elif parsed.path == "/send_pc":
            # GET /send_pc?program=120&channel=0
            prog = int(qs.get("program", ["0"])[0])
            ch   = int(qs.get("channel",  ["0"])[0])
            ok   = send_pc(ch, 0, 0, prog)
            self._json(200 if ok else 500, {"ok": ok, "program": prog})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            data = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except Exception as e:
            self._json(400, {"error": str(e)}); return

        if self.path == "/pc":
            ok = send_pc(int(data.get("channel",0)), int(data.get("bank_msb",0)),
                         int(data.get("bank_lsb",0)), int(data.get("program",0)))
            self._json(200 if ok else 500, {"ok": ok})
        elif self.path == "/cc":
            ok = send_cc(int(data.get("channel",0)), int(data.get("cc",0)),
                         int(data.get("value",0)))
            self._json(200 if ok else 500, {"ok": ok})
        else:
            self._json(404, {"error": "unknown endpoint"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port",      type=int, default=37432)
    parser.add_argument("--midi-port", type=str, default="AXE IO")
    args = parser.parse_args()

    print("─" * 50)
    print("  AT5 MIDI Bridge")
    print("─" * 50)
    print(f"  MIDI target : {args.midi_port}")
    print(f"  HTTP listen : http://localhost:{args.port}")
    print("─" * 50)

    init_midi(args.midi_port)

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    print(f"\nListening on http://localhost:{args.port}")
    print("  GET  /ping")
    print("  GET  /send_cc?cc=N&value=N[&channel=N]")
    print("  GET  /send_pc?program=N[&channel=N]")
    print("  POST /pc  {{channel, bank_msb, bank_lsb, program}}")
    print("  POST /cc  {{channel, cc, value}}")
    print("\nCtrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping...")
        winmm.midiOutClose(midi_out_handle)


if __name__ == "__main__":
    main()
