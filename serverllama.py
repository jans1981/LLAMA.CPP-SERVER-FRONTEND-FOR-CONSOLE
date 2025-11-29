import curses
import os
import time
import threading
import subprocess
import psutil
import signal
import datetime
import shutil  # Añadido para verificar si existe el ejecutable
from pathlib import Path

# ================= CONFIGURATION =================
# Directorio por defecto. Se puede cambiar dentro del programa.
DEFAULT_MODELS_DIR = "./models" 

# CORRECCIÓN AQUÍ: Quitamos el "./" para que busque en el PATH del sistema.
# Si estás en Windows y da problemas, prueba cambiarlo a "llama-server.exe"
LLAMA_SERVER_BIN = "llama-server" 
# =================================================

class LlamaTUI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.running = True
        self.server_process = None
        self.running_model_path = None 
        
        # Settings
        self.model_dir = os.path.abspath(DEFAULT_MODELS_DIR)
        self.backend = "CPU" 
        self.host_ip = "0.0.0.0"
        self.port = "8080"
        self.allow_lan = False
        self.schedule_time = "" 
        self.schedule_active = False
        
        # UI State
        self.active_field = 0 
        self.selected_file_idx = 0
        self.file_offset = 0
        self.files = []
        self.msg_log = "Welcome. Select a model and press 'S' to serve."
        
        # Initialize File List
        self.refresh_file_list()
        
        # Colors
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_RED, -1)
        curses.init_pair(4, curses.COLOR_CYAN, -1)
        curses.init_pair(5, curses.COLOR_GREEN, curses.COLOR_BLUE)

        curses.curs_set(0) 
        self.stdscr.nodelay(True) 

    def refresh_file_list(self):
        path = Path(self.model_dir)
        self.files = []
        if path.exists() and path.is_dir():
            # Get all .gguf files
            self.files = sorted([f for f in path.glob("*.gguf") if f.is_file()], key=lambda f: f.name)
            self.selected_file_idx = 0
            self.file_offset = 0
        else:
            self.msg_log = f"Error: Directory not found: {self.model_dir}"

    def get_ram_info(self):
        try:
            mem = psutil.virtual_memory()
            total_gb = mem.total / (1024**3)
            avail_gb = mem.available / (1024**3)
            percent = mem.percent
            return f"RAM: {avail_gb:.1f}GB Free / {total_gb:.1f}GB Total ({percent}%)"
        except:
            return "RAM: N/A"

    def get_file_size(self, path):
        try:
            size_gb = path.stat().st_size / (1024**3)
            return f"{size_gb:.2f} GB"
        except:
            return "?.?? GB"

    def kill_server(self):
        if self.server_process:
            try:
                # NOTA: os.killpg es específico de Unix/Linux/Mac. 
                # Si esto corre en Windows nativo, fallará y requerirá otro método.
                os.killpg(os.getpgid(self.server_process.pid), signal.SIGTERM)
                self.server_process = None
                self.running_model_path = None 
                return "Server stopped and cache cleared."
            except Exception as e:
                # Fallback para intentar matar el proceso si killpg falla
                try:
                    self.server_process.terminate()
                    self.server_process = None
                    self.running_model_path = None
                    return "Server stopped (fallback)."
                except:
                    return f"Error stopping: {e}"
        return "No server running."

    def start_server(self):
        if self.server_process:
            return "Server already running. Press 'K' first."
        
        if not self.files:
            return "No models found in current directory."
        
        # Verificación previa: ¿Existe el ejecutable en el PATH?
        if shutil.which(LLAMA_SERVER_BIN) is None:
             return f"Error: '{LLAMA_SERVER_BIN}' not found in PATH."

        current_file_obj = self.files[self.selected_file_idx]
        # CORRECCIÓN: .resolve() asegura la ruta absoluta completa para el servidor
        model_path = str(current_file_obj.resolve())
        
        cmd = [LLAMA_SERVER_BIN, "-m", model_path, "--port", self.port]
        
        if self.allow_lan:
            cmd.extend(["--host", self.host_ip])
        else:
            cmd.extend(["--host", "127.0.0.1"])

        if self.backend == "CUDA":
            cmd.extend(["-ngl", "99"]) 
        elif self.backend == "VULKAN":
            cmd.extend(["-ngl", "99"]) 

        try:
            # start_new_session=True es la alternativa moderna a preexec_fn=os.setsid
            # y funciona mejor en algunos entornos, aunque sigue siendo orientado a Unix.
            self.server_process = subprocess.Popen(
                cmd, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                start_new_session=True 
            )
            self.running_model_path = str(current_file_obj) 
            return f"SERVING: {current_file_obj.name}"
        except FileNotFoundError:
            return "Error: llama-server binary not found."
        except Exception as e:
            return f"Error: {str(e)}"

    def draw_box(self, y, x, h, w, title=""):
        try:
            self.stdscr.addstr(y, x, "┌" + "─" * (w-2) + "┐")
            for i in range(1, h-1):
                self.stdscr.addstr(y+i, x, "│" + " " * (w-2) + "│")
            self.stdscr.addstr(y+h-1, x, "└" + "─" * (w-2) + "┘")
            if title:
                self.stdscr.addstr(y, x+2, f" {title} ", curses.A_BOLD)
        except curses.error:
            pass

    def input_string(self, y, x, prompt, default_val):
        curses.echo()
        curses.curs_set(1)
        
        self.stdscr.move(y, 0)
        self.stdscr.clrtoeol()
        
        prompt_str = f"{prompt} [{default_val}]: "
        self.stdscr.addstr(y, x, prompt_str, curses.color_pair(4))
        self.stdscr.refresh()
        
        win = curses.newwin(1, 50, y, x + len(prompt_str))
        try:
            box = win.getstr().decode('utf-8').strip()
        except:
            box = ""
            
        curses.noecho()
        curses.curs_set(0)
        
        self.stdscr.move(y, 0)
        self.stdscr.clrtoeol()
        
        return box if box else default_val

    def check_schedule(self):
        if self.schedule_active and not self.server_process:
            now = datetime.datetime.now().strftime("%H:%M")
            if now == self.schedule_time:
                self.msg_log = self.start_server()
                time.sleep(60) 

    def run(self):
        while self.running:
            self.stdscr.clear()
            h, w = self.stdscr.getmaxyx()
            
            if h < 20 or w < 80:
                self.stdscr.addstr(0,0, "Window too small. Resize > 80x20")
                self.stdscr.refresh()
                time.sleep(0.5)
                continue

            header_text = f" LLAMA-SERVER TUI | {self.get_ram_info()} "
            self.stdscr.attron(curses.color_pair(1))
            self.stdscr.addstr(0, 0, header_text)
            try:
                self.stdscr.addstr(0, len(header_text), " " * (w - len(header_text)))
            except: pass
            self.stdscr.attroff(curses.color_pair(1))

            list_h = h - 8
            list_w = int(w * 0.65)
            sett_x = list_w + 1
            sett_w = w - list_w - 2

            self.draw_box(2, 0, list_h, list_w, f"GGUF Models ({len(self.files)})")
            
            max_items = list_h - 2
            if self.selected_file_idx < self.file_offset:
                self.file_offset = self.selected_file_idx
            elif self.selected_file_idx >= self.file_offset + max_items:
                self.file_offset = self.selected_file_idx - max_items + 1
                
            for i in range(max_items):
                file_idx = self.file_offset + i
                if file_idx >= len(self.files):
                    break
                
                f = self.files[file_idx]
                y_pos = 3 + i
                
                is_selected = (file_idx == self.selected_file_idx)
                is_running = (str(f) == self.running_model_path)
                
                # Prevenir errores de string fuera de limites
                display_str = f"{f.name[:list_w-16]} [{self.get_file_size(f)}]"
                
                if is_selected and is_running:
                    self.stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
                    self.stdscr.addstr(y_pos, 2, f"{display_str:<{list_w-4}}")
                    self.stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)
                elif is_selected:
                    self.stdscr.attron(curses.color_pair(1))
                    if self.active_field != 0: self.stdscr.attroff(curses.color_pair(1)) 
                    else: self.stdscr.attron(curses.A_BOLD)
                        
                    self.stdscr.addstr(y_pos, 2, f"{display_str:<{list_w-4}}")
                    self.stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
                elif is_running:
                    self.stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
                    self.stdscr.addstr(y_pos, 2, f"{display_str:<{list_w-4}}")
                    self.stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
                else:
                    self.stdscr.addstr(y_pos, 2, display_str)

            self.draw_box(2, sett_x, list_h, sett_w, "Configuration")
            
            def draw_setting(idx, y_off, label, value):
                style = curses.color_pair(1) if self.active_field == idx else curses.A_NORMAL
                self.stdscr.addstr(3 + y_off, sett_x + 2, label, style)
                self.stdscr.addstr(3 + y_off, sett_x + 2 + len(label), str(value))

            disp_dir = (self.model_dir[:sett_w-10] + '..') if len(self.model_dir) > sett_w-10 else self.model_dir
            
            draw_setting(1, 0, "Dir: ", disp_dir)
            draw_setting(2, 2, "Backend: ", f"[{self.backend}]")
            draw_setting(3, 4, "IP:      ", self.host_ip)
            draw_setting(4, 5, "Port:    ", self.port)
            
            lan_txt = "ENABLED" if self.allow_lan else "DISABLED"
            lan_col = curses.color_pair(2) if self.allow_lan else curses.color_pair(3)
            style_lbl = curses.color_pair(1) if self.active_field == 5 else curses.A_NORMAL
            self.stdscr.addstr(9, sett_x + 2, "LAN:     ", style_lbl)
            self.stdscr.addstr(9, sett_x + 11, lan_txt, lan_col)
            
            sched_txt = f"ON ({self.schedule_time})" if self.schedule_active else "OFF"
            draw_setting(6, 8, "Schedule: ", sched_txt)

            self.stdscr.addstr(13, sett_x + 2, "Server Status:", curses.A_UNDERLINE)
            if self.server_process:
                self.stdscr.addstr(14, sett_x + 2, "● RUNNING", curses.color_pair(2) | curses.A_BOLD)
                self.stdscr.addstr(15, sett_x + 2, f"PID: {self.server_process.pid}")
            else:
                self.stdscr.addstr(14, sett_x + 2, "● STOPPED", curses.color_pair(3))

            self.draw_box(h-6, 0, 6, w, "Controls")
            
            keys_hint = "TAB:Switch Section | ENTER:Edit/Select | ARROWS:Navigate"
            cmds_hint = "[S] START SERVER | [K] KILL SERVER | [Q] QUIT"
            
            self.stdscr.addstr(h-4, 2, keys_hint)
            self.stdscr.addstr(h-3, 2, cmds_hint, curses.A_BOLD)
            
            self.stdscr.addstr(h-2, 2, f"> {self.msg_log}", curses.color_pair(4))

            self.stdscr.refresh()
            self.check_schedule()

            try:
                key = self.stdscr.getch()
            except:
                key = -1

            if key == ord('q') or key == ord('Q'):
                self.kill_server()
                self.running = False
            
            elif key == ord('k') or key == ord('K'):
                self.msg_log = self.kill_server()

            elif key == ord('s') or key == ord('S'):
                self.msg_log = self.start_server()

            elif key == 9: 
                self.active_field = (self.active_field + 1) % 7
            
            elif key == curses.KEY_UP:
                if self.active_field == 0 and self.selected_file_idx > 0:
                    self.selected_file_idx -= 1
            
            elif key == curses.KEY_DOWN:
                if self.active_field == 0 and self.selected_file_idx < len(self.files) - 1:
                    self.selected_file_idx += 1

            elif key == 10: 
                if self.active_field == 1: 
                    new_dir = self.input_string(h-2, 2, "Full Path to Models:", self.model_dir)
                    if os.path.isdir(new_dir):
                        self.model_dir = os.path.abspath(new_dir) # Aseguramos absolute path al cambiar dir
                        self.refresh_file_list()
                        self.msg_log = "Directory updated."
                    else:
                        self.msg_log = "Invalid directory path."

                elif self.active_field == 2: 
                    modes = ["CPU", "CUDA", "VULKAN"]
                    curr_idx = modes.index(self.backend)
                    self.backend = modes[(curr_idx + 1) % len(modes)]
                
                elif self.active_field == 3: 
                    self.host_ip = self.input_string(h-2, 2, "Host IP:", self.host_ip)
                
                elif self.active_field == 4: 
                    self.port = self.input_string(h-2, 2, "Port:", self.port)

                elif self.active_field == 5: 
                    self.allow_lan = not self.allow_lan
                
                elif self.active_field == 6: 
                    if self.schedule_active:
                        self.schedule_active = False
                        self.msg_log = "Schedule disabled."
                    else:
                        t = self.input_string(h-2, 2, "Start Time (HH:MM):", "08:00")
                        try:
                            datetime.datetime.strptime(t, "%H:%M")
                            self.schedule_time = t
                            self.schedule_active = True
                            self.msg_log = f"Scheduled for {t}"
                        except ValueError:
                            self.msg_log = "Invalid time format. Use HH:MM"

            time.sleep(0.05)

def main():
    if not os.path.exists(DEFAULT_MODELS_DIR):
        try:
            os.makedirs(DEFAULT_MODELS_DIR)
        except:
            pass 

    try:
        curses.wrapper(lambda stdscr: LlamaTUI(stdscr).run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        # Si falla curses, imprime el error
        print(f"Fatal Error: {e}")

if __name__ == "__main__":
    main()
