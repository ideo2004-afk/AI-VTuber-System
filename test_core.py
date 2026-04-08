import AIVT_Core
import sys

try:
    print("Initializing AIVT_Core...")
    core = AIVT_Core.AIVT_Core()
    print("Initialization success!")
    sys.exit(0)
except Exception as e:
    import traceback
    traceback.print_exc()
    sys.exit(1)
