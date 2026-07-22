import sys, os
sys.path.insert(0, r'E:\Scripts\Stax')
from src.ingestion_core import SequenceDetector
p = r'E:\Temp\colorwgeel\imgs\1\img.0001.png'
print('Detecting for:', p)
res = SequenceDetector.detect_sequence(p, pattern_key=None, auto_detect=True)
print('Result:', res)
if res:
    print('Pattern key:', res.get('pattern_key'))
    print('Frame count:', res.get('frame_count'))
    print('First file:', res.get('files')[0])
