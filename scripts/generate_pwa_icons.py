#!/usr/bin/env python3
"""
Generador de iconos PWA para Axonote
Crea iconos médicos profesionales en todos los tamaños requeridos
"""

import os
import sys
from pathlib import Path

# Añadir PIL al path si está disponible
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️  PIL no disponible. Generando iconos SVG solamente.")

def create_svg_icon(size, icon_type="main"):
    """Genera un icono SVG médico profesional"""
    
    border_radius = int(size * 0.22)
    padding = int(size * 0.16)
    inner_size = size - (padding * 2)
    
    if icon_type == "main":
        # Icono principal de Axonote (estetoscopio + ondas)
        svg_content = f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="grad{size}" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#1d4ed8;stop-opacity:1" />
        </linearGradient>
        <filter id="shadow{size}" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="rgba(0,0,0,0.3)"/>
        </filter>
    </defs>
    
    <!-- Fondo con gradiente médico -->
    <rect width="{size}" height="{size}" rx="{border_radius}" fill="url(#grad{size})" filter="url(#shadow{size})"/>
    
    <g transform="translate({padding}, {padding})">
        <!-- Estetoscopio - Auricular izquierdo -->
        <circle cx="{inner_size * 0.3}" cy="{inner_size * 0.2}" r="{inner_size * 0.08}" 
                fill="none" stroke="white" stroke-width="{max(2, size//40)}"/>
        <circle cx="{inner_size * 0.3}" cy="{inner_size * 0.2}" r="{inner_size * 0.04}" fill="white"/>
        
        <!-- Estetoscopio - Auricular derecho -->
        <circle cx="{inner_size * 0.7}" cy="{inner_size * 0.2}" r="{inner_size * 0.08}" 
                fill="none" stroke="white" stroke-width="{max(2, size//40)}"/>
        <circle cx="{inner_size * 0.7}" cy="{inner_size * 0.2}" r="{inner_size * 0.04}" fill="white"/>
        
        <!-- Tubos del estetoscopio -->
        <path d="M{inner_size * 0.3} {inner_size * 0.28} Q{inner_size * 0.25} {inner_size * 0.45}, {inner_size * 0.35} {inner_size * 0.6}" 
              fill="none" stroke="white" stroke-width="{max(3, size//30)}" stroke-linecap="round"/>
        <path d="M{inner_size * 0.7} {inner_size * 0.28} Q{inner_size * 0.75} {inner_size * 0.45}, {inner_size * 0.65} {inner_size * 0.6}" 
              fill="none" stroke="white" stroke-width="{max(3, size//30)}" stroke-linecap="round"/>
        
        <!-- Campana del estetoscopio -->
        <circle cx="{inner_size * 0.5}" cy="{inner_size * 0.65}" r="{inner_size * 0.12}" 
                fill="white" stroke="white" stroke-width="{max(2, size//40)}"/>
        <circle cx="{inner_size * 0.5}" cy="{inner_size * 0.65}" r="{inner_size * 0.08}" 
                fill="none" stroke="#3b82f6" stroke-width="{max(1, size//60)}"/>
        
        <!-- Ondas de audio (visualización médica) -->
        <g transform="translate({inner_size * 0.2}, {inner_size * 0.82})">
            {"".join([
                f'<rect x="{i * inner_size * 0.06}" y="{inner_size * 0.08 - (i % 3) * inner_size * 0.03}" '
                f'width="{inner_size * 0.04}" height="{inner_size * 0.1 + (i % 4) * inner_size * 0.06}" '
                f'fill="#22c55e" rx="{inner_size * 0.02}" opacity="{0.9 - i * 0.1}"/>'
                for i in range(10)
            ])}
        </g>
        
        <!-- Texto "Ax" para tamaños grandes -->
        {f'<text x="{inner_size * 0.65}" y="{inner_size * 0.95}" fill="white" font-family="Arial, sans-serif" font-size="{size//8}" font-weight="bold">Ax</text>' if size >= 128 else ''}
        
        <!-- Indicador médico (cruz pequeña) -->
        <g transform="translate({inner_size * 0.85}, {inner_size * 0.15})">
            <rect x="-{inner_size * 0.03}" y="-{inner_size * 0.01}" width="{inner_size * 0.06}" height="{inner_size * 0.02}" fill="white" rx="{inner_size * 0.005}"/>
            <rect x="-{inner_size * 0.01}" y="-{inner_size * 0.03}" width="{inner_size * 0.02}" height="{inner_size * 0.06}" fill="white" rx="{inner_size * 0.005}"/>
        </g>
    </g>
</svg>'''
    
    elif icon_type == "record":
        # Icono de grabación
        svg_content = f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="gradRecord{size}" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#dc2626;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#991b1b;stop-opacity:1" />
        </linearGradient>
        <filter id="shadowRec{size}">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="rgba(0,0,0,0.3)"/>
        </filter>
    </defs>
    
    <rect width="{size}" height="{size}" rx="{border_radius}" fill="url(#gradRecord{size})" filter="url(#shadowRec{size})"/>
    
    <!-- Círculo de grabación principal -->
    <circle cx="{size//2}" cy="{size//2}" r="{size//3}" fill="white" opacity="0.95"/>
    <circle cx="{size//2}" cy="{size//2}" r="{size//4}" fill="#dc2626"/>
    
    <!-- Ondas de grabación -->
    <g transform="translate({size//2}, {size//2})">
        <circle r="{size//2.5}" fill="none" stroke="white" stroke-width="2" opacity="0.6">
            <animate attributeName="r" values="{size//2.5};{size//2.2};{size//2.5}" dur="1.5s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="0.6;0.2;0.6" dur="1.5s" repeatCount="indefinite"/>
        </circle>
        <circle r="{size//2.2}" fill="none" stroke="white" stroke-width="1.5" opacity="0.4">
            <animate attributeName="r" values="{size//2.2};{size//2};{size//2.2}" dur="2s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="0.4;0.1;0.4" dur="2s" repeatCount="indefinite"/>
        </circle>
    </g>
    
    <!-- Indicador REC -->
    <circle cx="{size * 0.8}" cy="{size * 0.2}" r="{size * 0.06}" fill="#ef4444"/>
    <text x="{size * 0.8}" y="{size * 0.35}" text-anchor="middle" fill="white" font-family="Arial, sans-serif" font-size="{size//12}" font-weight="bold">REC</text>
</svg>'''
    
    elif icon_type == "list":
        # Icono de lista
        svg_content = f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
    <defs>
        <linearGradient id="gradList{size}" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" style="stop-color:#059669;stop-opacity:1" />
            <stop offset="100%" style="stop-color:#047857;stop-opacity:1" />
        </linearGradient>
        <filter id="shadowList{size}">
            <feDropShadow dx="0" dy="2" stdDeviation="3" flood-color="rgba(0,0,0,0.3)"/>
        </filter>
    </defs>
    
    <rect width="{size}" height="{size}" rx="{border_radius}" fill="url(#gradList{size})" filter="url(#shadowList{size})"/>
    
    <g transform="translate({padding}, {padding})">
        <!-- Documentos apilados -->
        <rect x="{inner_size * 0.1}" y="{inner_size * 0.15}" width="{inner_size * 0.65}" height="{inner_size * 0.7}" rx="{inner_size * 0.05}" fill="white" opacity="0.3"/>
        <rect x="{inner_size * 0.15}" y="{inner_size * 0.1}" width="{inner_size * 0.65}" height="{inner_size * 0.7}" rx="{inner_size * 0.05}" fill="white" opacity="0.6"/>
        <rect x="{inner_size * 0.2}" y="{inner_size * 0.05}" width="{inner_size * 0.65}" height="{inner_size * 0.7}" rx="{inner_size * 0.05}" fill="white"/>
        
        <!-- Líneas de contenido médico -->
        <rect x="{inner_size * 0.25}" y="{inner_size * 0.2}" width="{inner_size * 0.45}" height="{inner_size * 0.025}" rx="{inner_size * 0.01}" fill="#059669"/>
        <rect x="{inner_size * 0.25}" y="{inner_size * 0.28}" width="{inner_size * 0.35}" height="{inner_size * 0.025}" rx="{inner_size * 0.01}" fill="#059669"/>
        <rect x="{inner_size * 0.25}" y="{inner_size * 0.36}" width="{inner_size * 0.4}" height="{inner_size * 0.025}" rx="{inner_size * 0.01}" fill="#059669"/>
        <rect x="{inner_size * 0.25}" y="{inner_size * 0.44}" width="{inner_size * 0.3}" height="{inner_size * 0.025}" rx="{inner_size * 0.01}" fill="#059669"/>
        <rect x="{inner_size * 0.25}" y="{inner_size * 0.52}" width="{inner_size * 0.42}" height="{inner_size * 0.025}" rx="{inner_size * 0.01}" fill="#059669"/>
        <rect x="{inner_size * 0.25}" y="{inner_size * 0.6}" width="{inner_size * 0.25}" height="{inner_size * 0.025}" rx="{inner_size * 0.01}" fill="#059669"/>
        
        <!-- Icono médico pequeño (estetoscopio mini) -->
        <g transform="translate({inner_size * 0.75}, {inner_size * 0.6})">
            <circle cx="0" cy="0" r="{inner_size * 0.04}" fill="#22c55e"/>
            <circle cx="0" cy="0" r="{inner_size * 0.025}" fill="white"/>
        </g>
        
        <!-- Indicador de audio -->
        <g transform="translate({inner_size * 0.75}, {inner_size * 0.25})">
            <rect x="-{inner_size * 0.01}" y="-{inner_size * 0.02}" width="{inner_size * 0.02}" height="{inner_size * 0.04}" fill="#3b82f6" rx="{inner_size * 0.005}"/>
            <rect x="{inner_size * 0.015}" y="-{inner_size * 0.015}" width="{inner_size * 0.02}" height="{inner_size * 0.03}" fill="#3b82f6" rx="{inner_size * 0.005}"/>
            <rect x="{inner_size * 0.04}" y="-{inner_size * 0.025}" width="{inner_size * 0.02}" height="{inner_size * 0.05}" fill="#3b82f6" rx="{inner_size * 0.005}"/>
        </g>
    </g>
</svg>'''
    
    return svg_content

def generate_png_from_svg(svg_content, size, output_path):
    """Convierte SVG a PNG usando cairosvg o método alternativo"""
    try:
        import cairosvg
        cairosvg.svg2png(bytestring=svg_content.encode('utf-8'), 
                        write_to=output_path, 
                        output_width=size, 
                        output_height=size)
        return True
    except ImportError:
        # Fallback: guardar como SVG si no hay cairosvg
        svg_path = output_path.replace('.png', '.svg')
        with open(svg_path, 'w', encoding='utf-8') as f:
            f.write(svg_content)
        print(f"⚠️  PNG conversion not available. Saved as SVG: {svg_path}")
        return False

def main():
    # Directorio de iconos
    icons_dir = Path('/home/javi/Programacion/axonote/apps/web/public/icons')
    icons_dir.mkdir(parents=True, exist_ok=True)
    
    print("🎨 Generando iconos PWA para Axonote...")
    print("=" * 50)
    
    # Tamaños de iconos requeridos por PWA
    main_sizes = [72, 96, 128, 144, 152, 192, 384, 512]
    special_icons = [
        ('record', 96, 'record-icon.png'),
        ('list', 96, 'list-icon.png')
    ]
    
    success_count = 0
    total_count = len(main_sizes) + len(special_icons)
    
    # Generar iconos principales
    for size in main_sizes:
        svg_content = create_svg_icon(size, "main")
        output_path = icons_dir / f'icon-{size}x{size}.png'
        
        print(f"📱 Generando {output_path.name}... ", end='')
        
        if generate_png_from_svg(svg_content, size, str(output_path)):
            print("✅ PNG")
            success_count += 1
        else:
            # Guardar SVG como fallback
            svg_path = icons_dir / f'icon-{size}x{size}.svg'
            with open(svg_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            print("📄 SVG")
            success_count += 1
    
    # Generar iconos especiales
    for icon_type, size, filename in special_icons:
        svg_content = create_svg_icon(size, icon_type)
        output_path = icons_dir / filename
        
        print(f"🎯 Generando {filename}... ", end='')
        
        if generate_png_from_svg(svg_content, size, str(output_path)):
            print("✅ PNG")
            success_count += 1
        else:
            # Guardar SVG como fallback
            svg_path = icons_dir / filename.replace('.png', '.svg')
            with open(svg_path, 'w', encoding='utf-8') as f:
                f.write(svg_content)
            print("📄 SVG")
            success_count += 1
    
    # Generar favicon.ico (copia del 32x32)
    favicon_svg = create_svg_icon(32, "main")
    favicon_path = icons_dir.parent / 'favicon.ico'
    
    print(f"🔗 Generando favicon.ico... ", end='')
    if generate_png_from_svg(favicon_svg, 32, str(favicon_path).replace('.ico', '.png')):
        # Intentar convertir PNG a ICO si PIL está disponible
        if PIL_AVAILABLE:
            try:
                img = Image.open(str(favicon_path).replace('.ico', '.png'))
                img.save(favicon_path, format='ICO', sizes=[(32, 32)])
                os.remove(str(favicon_path).replace('.ico', '.png'))
                print("✅ ICO")
            except Exception:
                print("📄 PNG (como favicon.png)")
        else:
            print("📄 PNG (como favicon.png)")
    else:
        print("📄 SVG")
    
    print("\n" + "=" * 50)
    print(f"🎉 Generación completada: {success_count}/{total_count} iconos")
    print(f"📁 Ubicación: {icons_dir}")
    
    # Verificar archivos generados
    print("\n📋 Archivos generados:")
    for file in sorted(icons_dir.rglob('*')):
        if file.is_file():
            size_kb = file.stat().st_size / 1024
            print(f"   {file.name} ({size_kb:.1f} KB)")
    
    print("\n✅ Los iconos están listos para la PWA de Axonote!")
    print("💡 Tip: Abre el generador HTML para ver los iconos en el navegador")

if __name__ == '__main__':
    main()
