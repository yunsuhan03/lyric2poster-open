import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CANARY = "Zebra-lantern quokka whispers over the copper orchard tonight"
LYRICS = (
    "The harbor lights are folding into rain\n"
    f"{CANARY}\n"
    "We keep the last train waiting at the door\n"
)
