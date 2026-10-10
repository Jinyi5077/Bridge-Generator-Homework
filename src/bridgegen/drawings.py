"""CAD export entry point and the legacy calculation-report font helper."""
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .engineering_drawings import export_drawings


def font_name():
    """Font used by calculation reports; CAD fonts are defined separately."""
    if 'BridgeCN' in pdfmetrics.getRegisteredFontNames():return 'BridgeCN'
    for p in [Path('C:/Windows/Fonts/simhei.ttf'),Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc')]:
        if p.exists():
            pdfmetrics.registerFont(TTFont('BridgeCN',str(p)));return 'BridgeCN'
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    if 'STSong-Light' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    return 'STSong-Light'
