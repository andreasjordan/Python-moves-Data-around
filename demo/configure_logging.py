import logging
import sys
from datetime import datetime

import pandas as pd


# The counterpart of PSFramework in the sibling repository, which is where every lib/ function
# sends its messages. Three things come with it, and stdlib logging happens to model all three:
#
#   Write-PSFMessage -Level Verbose  ->  logger.debug   hidden on screen, kept in the file
#   Write-PSFMessage -Level Warning  ->  logger.warning
#   Get-PSFMessage                   ->  MessageLog below, as a DataFrame
#
# The demo scripts on the other side use -Level Host for what the audience reads. Here the
# notebooks just print(), which needs no logger at all.


class MessageLog(logging.Handler):
    """Keeps every message so it can be queried afterwards, the way Get-PSFMessage does.

    The sibling can run

        Get-PSFMessage | Where-Object Message -like Finished*Milliseconds | Select-Object -Last 3

    to compare the timings of three imports. `pd.DataFrame(messages.records)` is that query,
    against a DataFrame - which is the shape this repository moves everything else around in.
    """

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append({
            "time": datetime.fromtimestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        })

    def to_frame(self):
        return pd.DataFrame(self.records, columns=["time", "level", "logger", "message"])


def configure_logging(level=logging.INFO, path="demo.log"):
    """Send lib/ messages to the screen, to a file, and to a MessageLog. Returns the MessageLog.

    `level` is what reaches the screen. INFO shows the bulk-load progress and nothing else;
    logging.DEBUG shows everything, which is the counterpart of -Verbose on the other side.
    The file always gets everything.
    """

    # sys.stdout on purpose. A StreamHandler writes to stderr by default, and Jupyter paints
    # stderr on a red background - so every progress line would look like an error on a projector.
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter("%(message)s"))

    logfile = logging.FileHandler(path, encoding="utf-8")
    logfile.setLevel(logging.DEBUG)
    logfile.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)-28s %(message)s"))

    messages = MessageLog()
    messages.setLevel(logging.DEBUG)

    # "lib" and not the root logger, so this configures the functions of this repository and not
    # psycopg, pymongo and confluent-kafka logging their own internals into the same file.
    #
    # Assigning the handler list rather than calling addHandler, because a notebook cell gets
    # re-run: addHandler would attach a second copy every time and each message would appear
    # twice, then three times. logging.basicConfig has the mirror-image trap - it does nothing
    # at all when a handler already exists, which in Jupyter it may.
    lib_logger = logging.getLogger("lib")
    lib_logger.setLevel(logging.DEBUG)
    lib_logger.handlers = [console, logfile, messages]

    return messages
