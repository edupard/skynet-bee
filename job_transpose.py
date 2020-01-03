import abstractions.job_queue as job_queue
import job_scheduler as jobs
from abstractions.daily_chunks_repo import ChunksRepo
import abstractions.constants as constants
import abstractions.file_storage as file_storage
import numpy as np
import os
import tempfile
import csv
import uuid
import sys
from abstractions.tickers import get_tickers
from abstractions.prices import TICKER_COLUMN

def write_data(daily_data):
    repo = ChunksRepo()

    for date, arr in daily_data.items():
        #y = date // 10000
        #m = (date % 10000) // 100
        #d = (date % 10000) % 100
        fd, tmp_file_name = tempfile.mkstemp()
        os.close(fd)
        with open(tmp_file_name, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(
                ['ticker', 'o', 'h', 'l', 'c', 'v', 'a_o', 'a_h', 'a_l',
                 'a_c', 'a_v', 'div', 'split'])
            for p in arr:
                ticker = p[0]
                o = p[1]
                h = p[2]
                l = p[3]
                c = p[4]
                v = p[5]
                a_o = p[6]
                a_h = p[7]
                a_l = p[8]
                a_c = p[9]
                a_v = p[10]
                div = p[11]
                split = p[12]
                writer.writerow([ticker, o, h, l, c, v, a_o, a_h, a_l, a_c, a_v, div, split])

        sUuid = str(uuid.uuid1())
        file_storage.put_file(tmp_file_name, constants.TEMP_BUCKET_NAME, f"{date}-{sUuid}.csv")
        repo.store_chunk(date, sUuid)
        os.remove(tmp_file_name)

def collect_data(ticker, daily_data, data):
    for idx in range(data.shape[0]):
        values = data[idx, :]
        # ['date', 'o', 'h', 'l', 'c', 'v', 'a_o', 'a_h', 'a_l', 'a_c', 'a_v', 'div', 'split'])
        date = int(values[0])
        o = values[1]
        h = values[2]
        l = values[3]
        c = values[4]
        v = values[5]
        a_o = values[6]
        a_h = values[7]
        a_l = values[8]
        a_c = values[9]
        a_v = values[10]
        div = values[11]
        split = values[12]

        if date in daily_data:
            arr = daily_data[date]
        else:
            arr = []
            daily_data[date] = arr
        arr.append([ticker, o, h, l, c, v, a_o, a_h, a_l, a_c, a_v, div, split])

index = int(sys.argv[1])
workers = 75
df = get_tickers()
tickers = df[TICKER_COLUMN].values
total = len(tickers)
batch_size = (total // workers) + 1
start = index * batch_size
stop = start + batch_size
to_process = tickers[start: stop]

daily_data = {}

for ticker in to_process:
    tmp_file_name = file_storage.get_file(constants.DAILY_DATA_BUCKET_NAME, f"{ticker}.csv")
    if tmp_file_name is None:
        continue
    # read file
    data = np.genfromtxt(tmp_file_name, delimiter=',', skip_header=1)
    print(f"{ticker}.csv - {tmp_file_name}")

    os.remove(tmp_file_name)

    collect_data(ticker, daily_data, data)
write_data(daily_data)

