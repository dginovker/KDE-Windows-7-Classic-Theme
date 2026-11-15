from html.parser import HTMLParser
from pathlib import Path
from PIL import Image

root = Path(__file__).resolve().parent

class Gallery(HTMLParser):
    def handle_starttag(self, tag, attributes):
        for key, value in attributes:
            if key not in ('src', 'href') or value.startswith('#'):
                continue
            path = (root/value).resolve()
            assert path.is_relative_to(root.parent) and path.is_file(), value
            if tag == 'img':
                with Image.open(path) as image:
                    assert image.size in {(1280,800), (405,461), (992,533)}, value

Gallery().feed((root/'gallery.html').read_text())
print('Gallery links and image dimensions verified.')
