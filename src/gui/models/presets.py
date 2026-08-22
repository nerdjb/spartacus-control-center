"""
Theme Presets - Production-ready themes for Spartacus LCD display
LCDWiki-style professional designs with data binding
"""

from models.theme import Theme, TextElement, GaugeElement, BackgroundElement, Color, Position, Size


class ThemePresets:
    """Factory class for creating preset themes"""
    
    @staticmethod
    def minimal() -> Theme:
        """Minimal theme - low resource, essential info only"""
        theme = Theme(
            name="Minimal",
            canvas_width=480,
            canvas_height=480,
            background=BackgroundElement(color=Color(10, 15, 40)),
        )
        
        # Title
        theme.add_element(TextElement(
            element_id="title",
            position=Position(240, 40),
            text="SPARTACUS",
            font_size=24,
            color=Color(0, 212, 255),
            bold=True,
        ))
        
        # CPU Gauge
        theme.add_element(GaugeElement(
            element_id="cpu_gauge",
            position=Position(240, 200),
            radius=80,
            data_source="cpu_temp",
            min_value=20,
            max_value=100,
            color_min=Color(0, 255, 136),
            color_max=Color(255, 100, 0),
            show_value=True,
        ))
        
        # CPU Label
        theme.add_element(TextElement(
            element_id="cpu_label",
            position=Position(240, 310),
            text="CPU: {value:.0f}°C",
            format_string="CPU: {value:.0f}°C",
            data_source="cpu_temp",
            font_size=16,
            color=Color(0, 212, 255),
        ))
        
        # Pump RPM
        theme.add_element(TextElement(
            element_id="pump_rpm",
            position=Position(240, 380),
            text="Pump: {value} RPM",
            format_string="Pump: {value} RPM",
            data_source="pump_rpm",
            font_size=14,
            color=Color(100, 200, 255),
        ))
        
        return theme
    
    @staticmethod
    def gaming() -> Theme:
        """Gaming theme - performance-focused, emphasizes dual temps"""
        theme = Theme(
            name="Gaming",
            canvas_width=480,
            canvas_height=480,
            background=BackgroundElement(color=Color(20, 25, 50)),
        )
        
        # Title with gaming style
        theme.add_element(TextElement(
            element_id="title",
            position=Position(240, 30),
            text="⚡ GAMING ⚡",
            font_size=20,
            color=Color(200, 100, 255),
            bold=True,
        ))
        
        # CPU Gauge (left)
        theme.add_element(GaugeElement(
            element_id="cpu_gauge",
            position=Position(120, 140),
            radius=60,
            data_source="cpu_temp",
            min_value=20,
            max_value=100,
            color_min=Color(0, 255, 136),
            color_max=Color(255, 100, 0),
            show_value=True,
        ))
        
        # CPU Label
        theme.add_element(TextElement(
            element_id="cpu_label",
            position=Position(120, 220),
            text="CPU",
            font_size=12,
            color=Color(0, 212, 255),
        ))
        
        # GPU Gauge (right)
        theme.add_element(GaugeElement(
            element_id="gpu_gauge",
            position=Position(360, 140),
            radius=60,
            data_source="gpu_temp",
            min_value=20,
            max_value=100,
            color_min=Color(0, 255, 136),
            color_max=Color(255, 100, 0),
            show_value=True,
        ))
        
        # GPU Label
        theme.add_element(TextElement(
            element_id="gpu_label",
            position=Position(360, 220),
            text="GPU",
            font_size=12,
            color=Color(255, 100, 255),
        ))
        
        # Pump RPM (center)
        theme.add_element(TextElement(
            element_id="pump_label",
            position=Position(240, 310),
            text="[PUMP]",
            font_size=12,
            color=Color(100, 200, 255),
        ))
        
        theme.add_element(TextElement(
            element_id="pump_rpm",
            position=Position(240, 340),
            text="{value} RPM",
            format_string="{value} RPM",
            data_source="pump_rpm",
            font_size=16,
            color=Color(200, 100, 255),
            bold=True,
        ))
        
        # Fan grid (6 fans)
        fan_positions = [
            (80, 400), (160, 400), (240, 400),
            (320, 400), (400, 400), (100, 450),
        ]
        
        for i, (x, y) in enumerate(fan_positions):
            theme.add_element(TextElement(
                element_id=f"fan_{i}_rpm",
                position=Position(x, y),
                text=f"F{i+1}: {'{value}'}",
                format_string=f"F{i+1}: {{value}}",
                data_source=f"fan_{i}_rpm",
                font_size=10,
                color=Color(100, 150, 255),
            ))
        
        return theme
    
    @staticmethod
    def cyberpunk() -> Theme:
        """Cyberpunk theme - neon aesthetic, high visual impact"""
        theme = Theme(
            name="Cyberpunk",
            canvas_width=480,
            canvas_height=480,
            background=BackgroundElement(color=Color(5, 5, 20)),
        )
        
        # Title with neon style
        theme.add_element(TextElement(
            element_id="title",
            position=Position(240, 25),
            text="█ CYBER █",
            font_size=22,
            color=Color(0, 255, 255),
            bold=True,
        ))
        
        # Neon divider (text line)
        theme.add_element(TextElement(
            element_id="divider",
            position=Position(240, 60),
            text="━━━━━━━━━━━━",
            font_size=10,
            color=Color(255, 100, 255),
        ))
        
        # CPU Temp (huge, cyan)
        theme.add_element(TextElement(
            element_id="cpu_temp_large",
            position=Position(120, 160),
            text="{value:.0f}°",
            format_string="{value:.0f}°",
            data_source="cpu_temp",
            font_size=48,
            color=Color(0, 255, 255),
            bold=True,
        ))
        
        theme.add_element(TextElement(
            element_id="cpu_label",
            position=Position(120, 200),
            text="CPU",
            font_size=10,
            color=Color(0, 255, 255),
        ))
        
        # GPU Temp (huge, magenta)
        theme.add_element(TextElement(
            element_id="gpu_temp_large",
            position=Position(360, 160),
            text="{value:.0f}°",
            format_string="{value:.0f}°",
            data_source="gpu_temp",
            font_size=48,
            color=Color(255, 100, 255),
            bold=True,
        ))
        
        theme.add_element(TextElement(
            element_id="gpu_label",
            position=Position(360, 200),
            text="GPU",
            font_size=10,
            color=Color(255, 100, 255),
        ))
        
        # Pump status
        theme.add_element(TextElement(
            element_id="pump_status",
            position=Position(240, 280),
            text="[PUMP]",
            font_size=11,
            color=Color(0, 200, 100),
        ))
        
        theme.add_element(TextElement(
            element_id="pump_rpm",
            position=Position(240, 310),
            text="{value} RPM",
            format_string="{value} RPM",
            data_source="pump_rpm",
            font_size=14,
            color=Color(0, 200, 100),
            bold=True,
        ))
        
        # Online indicator
        theme.add_element(TextElement(
            element_id="status",
            position=Position(240, 380),
            text="● ONLINE ●",
            font_size=11,
            color=Color(255, 100, 100),
        ))
        
        # System speed indicator
        theme.add_element(TextElement(
            element_id="footer",
            position=Position(240, 450),
            text="SYSTEM ACTIVE",
            font_size=10,
            color=Color(0, 255, 255),
        ))
        
        return theme
    
    @staticmethod
    def dashboard() -> Theme:
        """Dashboard theme - comprehensive, professional layout"""
        theme = Theme(
            name="Dashboard",
            canvas_width=480,
            canvas_height=480,
            background=BackgroundElement(color=Color(15, 20, 45)),
        )
        
        # Header
        theme.add_element(TextElement(
            element_id="header",
            position=Position(240, 20),
            text="SYSTEM MONITOR",
            font_size=18,
            color=Color(100, 180, 255),
            bold=True,
        ))
        
        # Temperature section header
        theme.add_element(TextElement(
            element_id="temp_header",
            position=Position(70, 50),
            text="TEMPERATURE",
            font_size=11,
            color=Color(0, 212, 255),
        ))
        
        # CPU Gauge
        theme.add_element(GaugeElement(
            element_id="cpu_gauge",
            position=Position(90, 130),
            radius=40,
            data_source="cpu_temp",
            min_value=20,
            max_value=100,
            color_min=Color(0, 255, 136),
            color_max=Color(255, 100, 0),
            show_value=True,
        ))
        
        # CPU Label
        theme.add_element(TextElement(
            element_id="cpu_label",
            position=Position(90, 185),
            text="CPU",
            font_size=10,
            color=Color(0, 212, 255),
        ))
        
        # GPU Gauge
        theme.add_element(GaugeElement(
            element_id="gpu_gauge",
            position=Position(320, 130),
            radius=40,
            data_source="gpu_temp",
            min_value=20,
            max_value=100,
            color_min=Color(0, 255, 136),
            color_max=Color(255, 100, 0),
            show_value=True,
        ))
        
        # GPU Label
        theme.add_element(TextElement(
            element_id="gpu_label",
            position=Position(320, 185),
            text="GPU",
            font_size=10,
            color=Color(0, 212, 255),
        ))
        
        # Cooling section header
        theme.add_element(TextElement(
            element_id="cooling_header",
            position=Position(70, 220),
            text="COOLING",
            font_size=11,
            color=Color(100, 200, 255),
        ))
        
        # Pump RPM
        theme.add_element(TextElement(
            element_id="pump_label",
            position=Position(100, 250),
            text="Pump:",
            font_size=10,
            color=Color(100, 200, 255),
        ))
        
        theme.add_element(TextElement(
            element_id="pump_rpm",
            position=Position(200, 250),
            text="{value}",
            format_string="{value}",
            data_source="pump_rpm",
            font_size=10,
            color=Color(100, 200, 255),
        ))
        
        # Fan speeds grid (simplified for space)
        fan_y = 280
        for i in range(3):
            theme.add_element(TextElement(
                element_id=f"fan_{i}_label",
                position=Position(100, fan_y + i*20),
                text=f"F{i+1}:",
                font_size=9,
                color=Color(100, 200, 255),
            ))
            
            theme.add_element(TextElement(
                element_id=f"fan_{i}_rpm",
                position=Position(200, fan_y + i*20),
                text="{value}",
                format_string="{value}",
                data_source=f"fan_{i}_rpm",
                font_size=9,
                color=Color(100, 200, 255),
            ))
        
        # Footer
        theme.add_element(TextElement(
            element_id="footer",
            position=Position(240, 450),
            text="Real-time System Monitoring",
            font_size=9,
            color=Color(0, 212, 255),
        ))
        
        return theme
    
    @staticmethod
    def media() -> Theme:
        """Media theme - music/album art display with system stats"""
        theme = Theme(
            name="Media",
            canvas_width=480,
            canvas_height=480,
            background=BackgroundElement(color=Color(10, 10, 25)),
        )
        
        # Title
        theme.add_element(TextElement(
            element_id="title",
            position=Position(240, 30),
            text="🎵 ALBUM ART 🎵",
            font_size=18,
            color=Color(200, 100, 200),
            bold=True,
        ))
        
        # Album art placeholder
        theme.add_element(TextElement(
            element_id="album_placeholder",
            position=Position(240, 150),
            text="[Album Art Area]",
            font_size=12,
            color=Color(100, 100, 100),
        ))
        
        # Track info
        theme.add_element(TextElement(
            element_id="track",
            position=Position(240, 220),
            text="Track Name",
            font_size=11,
            color=Color(200, 150, 200),
        ))
        
        theme.add_element(TextElement(
            element_id="artist",
            position=Position(240, 240),
            text="Artist Name",
            font_size=10,
            color=Color(150, 100, 150),
        ))
        
        # System stats overlay
        theme.add_element(TextElement(
            element_id="cpu_stat",
            position=Position(70, 310),
            text="CPU: {value:.0f}°",
            format_string="CPU: {value:.0f}°",
            data_source="cpu_temp",
            font_size=10,
            color=Color(0, 212, 255),
        ))
        
        theme.add_element(TextElement(
            element_id="gpu_stat",
            position=Position(240, 310),
            text="GPU: {value:.0f}°",
            format_string="GPU: {value:.0f}°",
            data_source="gpu_temp",
            font_size=10,
            color=Color(255, 100, 255),
        ))
        
        theme.add_element(TextElement(
            element_id="pump_stat",
            position=Position(400, 310),
            text="P: {value}",
            format_string="P: {value}",
            data_source="pump_rpm",
            font_size=10,
            color=Color(100, 200, 100),
        ))
        
        # Footer
        theme.add_element(TextElement(
            element_id="footer",
            position=Position(240, 450),
            text="System Info - Secondary",
            font_size=8,
            color=Color(100, 100, 100),
        ))
        
        return theme
    
    @staticmethod
    def get_all_themes() -> dict:
        """Get all available preset themes"""
        return {
            "minimal": ThemePresets.minimal(),
            "gaming": ThemePresets.gaming(),
            "cyberpunk": ThemePresets.cyberpunk(),
            "dashboard": ThemePresets.dashboard(),
            "media": ThemePresets.media(),
        }
    
    @staticmethod
    def save_all_presets(output_dir):
        """Export all preset themes to JSON files"""
        from pathlib import Path
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for name, theme in ThemePresets.get_all_themes().items():
            theme.save(output_path / f"{name}_theme.json")
