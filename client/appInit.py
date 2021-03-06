import concurrent.futures
from client.db.initDb import initDatabase
import time


class AppInit:
    @classmethod
    def initialize(cls):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(cls.__initWork)
            initStatus = future.result()
            # time.sleep(5)
            return initStatus

    @staticmethod
    def __initWork():
        print("Some init work, waiting for 5 seconds...")
        return initDatabase()
        # return False
