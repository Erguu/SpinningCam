"""
Reusable scrollable frame base class for tab panels.
Extracts common canvas/scrollbar setup logic used by ProcessTab and MachineTab.
"""
import tkinter as tk
from tkinter import ttk


class ScrollableTabBase:
    """
    Base class providing a scrollable content area for tab panels.
    
    Subclasses should:
    1. Call super().__init__(parent_frame) in their __init__
    2. Use self.content as the parent for all widgets
    3. Override _create_widgets() to build UI
    """
    
    def __init__(self, parent_frame):
        """
        Initialize the scrollable area.
        
        Args:
            parent_frame: The parent tkinter Frame to embed this tab in.
        """
        self._parent_frame = parent_frame
        
        # Create Container Frame
        container = tk.Frame(parent_frame)
        container.pack(fill="both", expand=True)
        
        # Create Canvas with background
        self.canvas = tk.Canvas(container, bg="#f8f8f8", highlightthickness=0)
        
        # Create visible Scrollbar (tk instead of ttk for visibility)
        self.scrollbar = tk.Scrollbar(container, orient="vertical", command=self.canvas.yview, 
                                       width=16, bg="#cccccc", activebackground="#888888")
        
        # Content frame inside canvas
        self.content = ttk.Frame(self.canvas)

        # Window inside canvas
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        
        # Configure scroll region when content changes
        self.content.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        
        # Link scrollbar to canvas
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Pack scrollbar FIRST (right side), then canvas fills rest
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        
        # Ensure content frame width matches canvas width
        def on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        self.canvas.bind("<Configure>", on_canvas_configure)
        
        # Bind mouse wheel scrolling (Windows)
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        self.canvas.bind_all("<MouseWheel>", _on_mousewheel)

    def _create_widgets(self):
        """
        Build the UI widgets. Override in subclasses.
        """
        pass
    
    def refresh_ui(self):
        """
        Destroy and recreate all widgets from current params.
        """
        for widget in self.content.winfo_children():
            widget.destroy()
        self._create_widgets()
