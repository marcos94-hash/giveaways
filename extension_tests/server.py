import http.server, sys, os
LOG = sys.argv[2]
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *a):
        with open(LOG, "a") as f: f.write(self.path + "\n")
os.chdir(sys.argv[1])
http.server.ThreadingHTTPServer(("0.0.0.0", 8123), H).serve_forever()
