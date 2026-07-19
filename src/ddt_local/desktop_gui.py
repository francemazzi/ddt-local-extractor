"""Desktop onboarding wizard and compact dashboard for non-technical users."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Callable

from ddt_local.desktop_services import (
    DesktopSetupController,
    DesktopSetupError,
    OllamaReadiness,
)
from ddt_local.ollama import PullProgress

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"


def main() -> int:
    """Start the graphical application; packaged builds use a windowed executable."""
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ModuleNotFoundError:
        # This only affects development Python installations built without Tcl/Tk.
        # User-facing packaged applications include the GUI runtime.
        return 1

    root = tk.Tk()
    root.title("DDT Local Extractor")
    root.minsize(570, 380)
    root.resizable(False, False)
    DesktopApplication(root, ttk, filedialog, messagebox, DesktopSetupController()).show_initial()
    root.mainloop()
    return 0


class DesktopApplication:
    """Tkinter views; business behaviour remains in ``DesktopSetupController``."""

    def __init__(
        self,
        root: Any,
        ttk: Any,
        filedialog: Any,
        messagebox: Any,
        controller: DesktopSetupController,
    ) -> None:
        self.root = root
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.controller = controller
        self.frame = ttk.Frame(root, padding=24)
        self.frame.pack(fill="both", expand=True)
        self.selected_directory: Path | None = None
        self.selected_config = None
        self.progress_text = None

    def show_initial(self) -> None:
        status = self.controller.status()
        if status.configured and status.ready:
            self.show_dashboard()
        else:
            self.show_wizard()

    def _clear(self) -> None:
        for child in self.frame.winfo_children():
            child.destroy()

    def show_wizard(self) -> None:
        self._clear()
        self.ttk.Label(self.frame, text="Benvenuto in DDT Local Extractor", font=("TkDefaultFont", 18, "bold")).pack(
            anchor="w"
        )
        self.ttk.Label(
            self.frame,
            text="Scegli una cartella: l'app creerà inbox, archivio, database ed Excel al suo interno.",
            wraplength=500,
        ).pack(anchor="w", pady=(8, 18))

        self.progress_text = self._string_var("1. Scegli la cartella DDT")
        self.ttk.Label(self.frame, textvariable=self.progress_text, foreground="#1d4ed8").pack(anchor="w")
        folder_row = self.ttk.Frame(self.frame)
        folder_row.pack(fill="x", pady=(8, 16))
        self.directory_text = self._string_var("Nessuna cartella selezionata")
        self.ttk.Label(folder_row, textvariable=self.directory_text, wraplength=370).pack(
            side="left", fill="x", expand=True
        )
        self.ttk.Button(folder_row, text="Scegli cartella…", command=self.choose_directory).pack(side="right")

        actions = self.ttk.Frame(self.frame)
        actions.pack(fill="x", pady=(4, 10))
        self.ttk.Button(actions, text="Prepara cartella", command=self.prepare_directory).pack(side="left")
        self.ttk.Button(actions, text="Installa Ollama", command=self.open_ollama_download).pack(
            side="left", padx=(8, 0)
        )
        self.ttk.Button(actions, text="Riprova verifica", command=self.check_ollama).pack(
            side="left", padx=(8, 0)
        )

        self.models_button = self.ttk.Button(
            self.frame,
            text="Scarica modelli necessari",
            command=self.download_models,
            state="disabled",
        )
        self.models_button.pack(anchor="w", pady=(6, 14))
        self.finish_button = self.ttk.Button(
            self.frame,
            text="Completa e attiva elaborazione automatica",
            command=self.complete_setup,
            state="disabled",
        )
        self.finish_button.pack(anchor="w")
        self.ttk.Label(
            self.frame,
            text="L'elaborazione controllerà la inbox ogni 5 minuti. Puoi sempre forzarla dalla dashboard.",
            wraplength=500,
        ).pack(anchor="w", pady=(10, 0))

        # The portable launchers promise a first-run folder choice. Showing the
        # native picker immediately keeps that promise while leaving the button
        # available if the user cancels it.
        self.root.after(150, self.choose_directory)

    def choose_directory(self) -> None:
        selected = self.filedialog.askdirectory(
            title="Scegli la cartella DDT",
            mustexist=False,
        )
        if not selected:
            return
        self.selected_directory = Path(selected)
        self.directory_text.set(str(self.selected_directory))
        self.progress_text.set("2. Prepara la cartella selezionata")

    def prepare_directory(self) -> None:
        if self.selected_directory is None:
            self.messagebox.showinfo("Cartella DDT", "Prima scegli una cartella.")
            return
        try:
            self.selected_config = self.controller.selected_config(self.selected_directory)
        except DesktopSetupError as exc:
            self.messagebox.showerror("Cartella non disponibile", str(exc))
            return
        self.progress_text.set("3. Verifica Ollama e i modelli")
        self.check_ollama()

    def check_ollama(self) -> None:
        if self.selected_config is None:
            self.messagebox.showinfo("Cartella DDT", "Prima prepara la cartella scelta.")
            return
        try:
            readiness = self.controller.readiness(self.selected_config)
        except Exception as exc:
            self.messagebox.showerror("Verifica Ollama", str(exc))
            return
        self._show_readiness(readiness)

    def _show_readiness(self, readiness: OllamaReadiness) -> None:
        if not readiness.available:
            self.progress_text.set("Ollama non è disponibile: installalo, poi premi Riprova verifica.")
            self.models_button.configure(state="disabled")
            self.finish_button.configure(state="disabled")
            return
        if readiness.missing_models:
            self.progress_text.set("Modelli mancanti: " + ", ".join(readiness.missing_models))
            self.models_button.configure(state="normal")
            self.finish_button.configure(state="disabled")
            return
        self.progress_text.set("Tutto pronto. Attiva l'elaborazione automatica.")
        self.models_button.configure(state="disabled")
        self.finish_button.configure(state="normal")

    def open_ollama_download(self) -> None:
        webbrowser.open(OLLAMA_DOWNLOAD_URL)

    def download_models(self) -> None:
        if self.selected_config is None:
            return
        self.models_button.configure(state="disabled")
        self.progress_text.set("Avvio il download dei modelli…")

        def work() -> None:
            try:
                readiness = self.controller.download_missing_models(
                    self.selected_config,
                    progress=self._model_progress,
                )
                self.root.after(0, lambda: self._show_readiness(readiness))
            except Exception as exc:
                self.root.after(0, lambda: self._download_failed(str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _model_progress(self, model: str, event: PullProgress) -> None:
        percentage = ""
        if event.completed is not None and event.total:
            percentage = f" ({event.completed * 100 // event.total}%)"
        self.root.after(0, lambda: self.progress_text.set(f"{model}: {event.status}{percentage}"))

    def _download_failed(self, message: str) -> None:
        self.models_button.configure(state="normal")
        self.messagebox.showerror("Download modelli", message)

    def complete_setup(self) -> None:
        if self.selected_directory is None:
            return
        try:
            self.controller.complete_setup(self.selected_directory)
        except DesktopSetupError as exc:
            self.messagebox.showerror("Configurazione incompleta", str(exc))
            return
        self.show_dashboard()

    def show_dashboard(self) -> None:
        self._clear()
        status = self.controller.status()
        self.ttk.Label(self.frame, text="DDT Local Extractor", font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        home_text = str(status.ddt_home) if status.ddt_home else "Non configurato"
        state_text = "Pronto" if status.ready else "Richiede attenzione"
        self.ttk.Label(self.frame, text=f"Stato: {state_text}").pack(anchor="w", pady=(10, 0))
        self.ttk.Label(self.frame, text=f"Cartella DDT: {home_text}", wraplength=510).pack(anchor="w")
        self.ttk.Label(
            self.frame,
            text="Elaborazione automatica ogni 5 minuti" if status.scheduler_enabled else "Automazione non attiva",
        ).pack(anchor="w", pady=(0, 16))

        buttons = self.ttk.Frame(self.frame)
        buttons.pack(anchor="w")
        self.ttk.Button(buttons, text="Apri inbox", command=lambda: self.open_path(status.ddt_home / "inbox")).grid(
            row=0, column=0, padx=(0, 8), pady=4
        )
        self.ttk.Button(buttons, text="Apri Excel", command=lambda: self.open_excel(status.ddt_home)).grid(
            row=0, column=1, padx=(0, 8), pady=4
        )
        self.ttk.Button(buttons, text="Elabora ora", command=self.run_now).grid(row=0, column=2, pady=4)
        self.ttk.Button(self.frame, text="Impostazioni", command=self.change_directory).pack(anchor="w", pady=(10, 0))

    def open_excel(self, ddt_home: Path | None) -> None:
        if ddt_home is None:
            return
        path = ddt_home / "output" / "DDT_estratti.xlsx"
        if not path.exists():
            self.messagebox.showinfo("Excel", "L'Excel sarà creato con la prima elaborazione.")
            return
        self.open_path(path)

    def open_path(self, path: Path | None) -> None:
        if path is None:
            return
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            self.messagebox.showerror("Apri cartella", str(exc))

    def run_now(self) -> None:
        self.messagebox.showinfo("Elaborazione", "L'elaborazione è iniziata in background.")

        def work() -> None:
            try:
                summary = self.controller.run_now()
                self.root.after(
                    0,
                    lambda: self.messagebox.showinfo(
                        "Elaborazione completata",
                        f"Elaborati: {summary.processed}\nErrori: {summary.errors}\nDuplicati: {summary.duplicates}",
                    ),
                )
            except Exception as exc:
                self.root.after(0, lambda: self.messagebox.showerror("Elaborazione", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def change_directory(self) -> None:
        current = self.controller.status().ddt_home
        selected = self.filedialog.askdirectory(title="Scegli una nuova cartella DDT", mustexist=False)
        if not selected:
            return
        selected_path = Path(selected)
        if current and selected_path.resolve() == current.resolve():
            return
        confirmed = self.messagebox.askyesno(
            "Cambia cartella",
            "La nuova cartella verrà preparata senza spostare lo storico nella cartella attuale. Continuare?",
        )
        if not confirmed:
            return
        try:
            self.controller.complete_setup(selected_path)
        except DesktopSetupError as exc:
            self.messagebox.showerror("Cambia cartella", str(exc))
            return
        self.show_dashboard()

    def _string_var(self, value: str) -> Any:
        import tkinter as tk

        return tk.StringVar(master=self.root, value=value)


if __name__ == "__main__":
    raise SystemExit(main())
