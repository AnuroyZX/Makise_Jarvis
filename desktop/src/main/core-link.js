"use strict";

const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

/**
 * Manages the Python Amadeus Core subprocess (`--headless`) and parses its
 * `AMADEUS_READY ws_port=<port> ws_token=<token> http_url=<url>` stdout line.
 */
class CoreProcessLink {
  constructor({ projectRoot, onReady, onExit }) {
    this.projectRoot = projectRoot;
    this.onReady = onReady;
    this.onExit = onExit;
    this.proc = null;
    this.wsPort = 0;
    this.wsToken = "";
    this.httpUrl = "";
    this.restarts = 0;
    this.maxRestarts = 3;
    this.stopping = false;
  }

  resolveCommand() {
    // 0. Packaged electron app extraResources path
    const packagedEngineExe = path.join(process.resourcesPath || "", "engine", "AmadeusKurisu.exe");
    if (fs.existsSync(packagedEngineExe)) {
      const engineDir = path.dirname(packagedEngineExe);
      const engineDataDir = path.join(engineDir, "data");
      const env = {
        ...process.env,
        ...(fs.existsSync(engineDataDir) ? { AMADEUS_DATA_DIR: engineDataDir } : {}),
      };
      return {
        cmd: packagedEngineExe,
        args: ["--headless"],
        cwd: engineDir,
        env,
      };
    }

    const distDataDir = path.join(this.projectRoot, "dist", "AmadeusKurisu", "data");
    const env = {
      ...process.env,
      ...(fs.existsSync(distDataDir) ? { AMADEUS_DATA_DIR: distDataDir } : {}),
    };

    // 1. Prefer local .venv python when running inside development workspace for instant code sync
    const venvPy = path.join(this.projectRoot, ".venv", "Scripts", "python.exe");
    if (fs.existsSync(venvPy)) {
      return {
        cmd: venvPy,
        args: ["-m", "amadeus.main", "--headless"],
        cwd: this.projectRoot,
        env,
      };
    }

    // 2. Otherwise use compiled portable exe
    const portableExe = path.join(
      this.projectRoot,
      "dist",
      "AmadeusKurisu",
      "AmadeusKurisu.exe"
    );
    if (fs.existsSync(portableExe)) {
      return {
        cmd: portableExe,
        args: ["--headless"],
        cwd: path.dirname(portableExe),
        env,
      };
    }

    return {
      cmd: "python",
      args: ["-m", "amadeus.main", "--headless"],
      cwd: this.projectRoot,
      env,
    };
  }

  start() {
    this.stopping = false;
    const { cmd, args, env, cwd } = this.resolveCommand();
    this.proc = spawn(cmd, args, {
      cwd: cwd || this.projectRoot,
      env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });

    let buffer = "";
    this.proc.stdout.on("data", (chunk) => {
      buffer += chunk.toString("utf-8");
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("AMADEUS_READY ")) {
          const portMatch = line.match(/ws_port=(\d+)/);
          const tokenMatch = line.match(/ws_token=([^\s]+)/);
          const urlMatch = line.match(/http_url=([^\s]+)/);
          if (portMatch && tokenMatch && urlMatch) {
            this.wsPort = parseInt(portMatch[1], 10);
            this.wsToken = tokenMatch[1];
            this.httpUrl = urlMatch[1];
            if (this.onReady) {
              this.onReady({
                wsPort: this.wsPort,
                wsToken: this.wsToken,
                httpUrl: this.httpUrl,
              });
            }
          }
        }
      }
    });

    this.proc.stderr.on("data", (chunk) => {
      console.error("[PYTHON-CORE]", chunk.toString("utf-8").trim());
    });

    this.proc.on("exit", (code) => {
      if (!this.stopping && this.restarts < this.maxRestarts) {
        this.restarts += 1;
        setTimeout(() => this.start(), 1000);
        return;
      }
      if (this.onExit) this.onExit(code);
    });
  }

  stop() {
    this.stopping = true;
    if (this.proc && !this.proc.killed) {
      try {
        this.proc.kill();
      } catch (_) {}
    }
  }
}

module.exports = { CoreProcessLink };
