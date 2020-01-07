import abstractions.job_queue as job_queue
import job_scheduler as jobs
from abstractions.log import log
import abstractions.file_storage as file_storage
import abstractions.constants as constants
import os
import numpy as np
import datetime
from utils.utils import arr_rema, i_to_date, roll_arr_fwd
import math
import tempfile

#https://www.youtube.com/watch?v=ffDLG7Vt6JE&t=18s

ANN_FACTOR = 252.75

def get_indexes(i_dates: np.ndarray, min_date: datetime.date):
    indexes = np.zeros_like(i_dates)
    idx = 0
    for i in i_dates:
        indexes[idx] = (i_to_date(i_dates[idx]) - min_date).days
        idx = idx + 1
    return indexes

def get_raw_data(min_date: datetime.date, max_date: datetime.date, indexes: np.ndarray, data: np.ndarray):

    total_points = (max_date - min_date).days + 1
    # ['v', 't', 'a_o', 'a_h', 'a_l', 'a_c']
    raw = np.zeros((total_points, 6))
    # no trading activity interpreted as very small quantity
    raw[:,0] = 100
    # ['date', 'o', 'h', 'l', 'c', 'v', 'a_o', 'a_h', 'a_l', 'a_c', 'a_v', 'div', 'split']
    raw[indexes,0] = data[:,5]
    raw[indexes,1] = (data[:,2] + data[:,3] + data[:,4]) / 3
    raw[indexes, 2] = data[:,6]
    raw[indexes, 3] = data[:,7]
    raw[indexes, 4] = data[:,8]
    raw[indexes, 5] = data[:,9]

    zero_prices_mask = raw[:, 5] == 0
    # roll closing price
    raw[:, 5] = roll_arr_fwd(raw[:, 5])
    # copy closing price if other prices is missing
    raw[zero_prices_mask, 1] = raw[zero_prices_mask, 5]
    raw[zero_prices_mask, 2] = raw[zero_prices_mask, 5]
    raw[zero_prices_mask, 3] = raw[zero_prices_mask, 5]
    raw[zero_prices_mask, 4] = raw[zero_prices_mask, 5]

    return raw

def get_input_from_raw(raw):
    gv = raw[:, 0] * raw[:, 1]
    a_o = raw[:, 2]
    a_h = raw[:, 3]
    a_l = raw[:, 4]
    a_c = raw[:, 5]

    a_c_0 = a_c[0]
    a_c_t_min_1 = np.roll(a_c, 1, axis=0)
    a_c_t_min_1[0] = a_c_0

    gv_0 = gv[0]
    gv_t_min_1 = np.roll(gv, 1, axis=0)
    gv_t_min_1[0] = gv_0

    lr_o = np.log(a_o / a_c_t_min_1)
    lr_h = np.log(a_h / a_c_t_min_1)
    lr_l = np.log(a_l / a_c_t_min_1)
    lr_c = np.log(a_c / a_c_t_min_1)
    lr_gv = np.log(gv / gv_t_min_1)

    result = np.stack([lr_o, lr_h, lr_l, lr_c, lr_gv], axis=1)
    return result

def get_output(raw, gamma):
    #gv, t, a_o, a_h, a_l, a_c
    a_c = raw[:, 5]
    a_c_0 = a_c[0]
    a_c_t_min_1 = np.roll(a_c, 1, axis=0)
    a_c_t_min_1[0] = a_c_0

    lr_c = np.log(a_c / a_c_t_min_1)
    sigma = lr_c * lr_c

    lr_c_t__plus_1 = np.roll(lr_c, -1, axis=0)
    lr_c_t__plus_1[-1] = 0
    sigma_t_plus_1 = np.roll(sigma, -1, axis=0)
    sigma_t_plus_1[-1] = 0

    lr_rema = arr_rema(lr_c_t__plus_1, gamma)
    sigma_rema = arr_rema(sigma_t_plus_1, gamma)
    stddev_rema = np.sqrt(sigma_rema)
    lr_rema_ann = ANN_FACTOR * lr_rema
    stddev_rema_ann = math.sqrt(ANN_FACTOR) * stddev_rema

    return np.stack([lr_rema_ann,
              stddev_rema_ann], axis=1)

def save(ticker, spy_dates, spy_input, raw_input, raw_output, gamma):
    result = np.hstack([np.reshape(spy_dates, (-1,1)), spy_input, raw_input, raw_output])
    fd, tmp_file_name = tempfile.mkstemp()
    os.close(fd)

    #savetxt(fname, X, fmt='%.18e', delimiter=' ', newline='\n', header='',footer='', comments='# ', encoding=None):
    np.savetxt(tmp_file_name,
               result,
               fmt='%.0f %.18e %.18e %.18e %.18e %.18e %.18e %.18e %.18e %.18e %.18e %.18e %.18e',
               delimiter=',',
               comments='',
               header='date,spy_lr_o,spy_lr_h,spy_lr_l,spy_lr_c,spy_lr_gv,lr_o,lr_h,lr_l,lr_c,lr_gv,p_lr,p_std')
    file_storage.put_file(tmp_file_name, constants.DATA_BUCKET_NAME, f"ds/{ticker}_{gamma}.csv")
    os.remove(tmp_file_name)

def preprocess(ticker, tmp_file_name, spy_tmp_file_name):
    data = np.reshape(np.genfromtxt(tmp_file_name, delimiter=',', skip_header=1), (-1, 13))
    spy_data = np.reshape(np.genfromtxt(spy_tmp_file_name, delimiter=',', skip_header=1), (-1, 13))
    # ['date', 'o', 'h', 'l', 'c', 'v', 'a_o', 'a_h', 'a_l', 'a_c', 'a_v', 'div', 'split']

    spy_dates = spy_data[:, 0]
    i_spy_dates = spy_dates.astype(np.int)
    i_dates = data[:, 0].astype(np.int)
    i_min_date = min(i_spy_dates[0], i_dates[0])
    i_max_date = max(i_spy_dates[-1], i_dates[-1])
    min_date = i_to_date(i_min_date)
    max_date = i_to_date(i_max_date)

    spy_indexes = get_indexes(i_spy_dates, min_date)
    indexes = get_indexes(i_dates, min_date)

    spy_raw = get_raw_data(min_date, max_date, spy_indexes, spy_data)
    raw = get_raw_data(min_date, max_date, indexes, data)

    spy_raw = spy_raw[spy_indexes, :]
    raw = raw[spy_indexes, :]

    # ['v', 't', 'a_o', 'a_h', 'a_l', 'a_c']
    spy_input = get_input_from_raw(spy_raw)
    raw_input = get_input_from_raw(raw)
    raw_output_95 = get_output(raw, 0.95)
    raw_output_90 = get_output(raw, 0.90)
    raw_output_80 = get_output(raw, 0.80)
    raw_output_70 = get_output(raw, 0.70)
    raw_output_50 = get_output(raw, 0.5)
    raw_output_00 = get_output(raw, 0.0)

    save(ticker, spy_dates, spy_input, raw_input, raw_output_95, 95)
    save(ticker, spy_dates, spy_input, raw_input, raw_output_90, 90)
    save(ticker, spy_dates, spy_input, raw_input, raw_output_80, 80)
    save(ticker, spy_dates, spy_input, raw_input, raw_output_70, 70)
    save(ticker, spy_dates, spy_input, raw_input, raw_output_50, 50)
    save(ticker, spy_dates, spy_input, raw_input, raw_output_00, 0)


spy_tmp_file_name = None

while True:
    messages, to_ack = job_queue.pull_job_queue_items(jobs.PREPROCESS_QUEUE, 1)
    if len(messages) == 0:
        break
    for ticker in messages:
        tmp_file_name = file_storage.get_file(constants.DATA_BUCKET_NAME, f"stocks/{ticker}.csv")
        if tmp_file_name is None:
            continue
        if spy_tmp_file_name is None:
            spy_tmp_file_name = file_storage.get_file(constants.DATA_BUCKET_NAME, "stocks/SPY.csv")
        log(f"Preprocessing {ticker} stock data")
        preprocess(ticker, tmp_file_name, spy_tmp_file_name)
        os.remove(tmp_file_name)

    job_queue.ack(jobs.PREPROCESS_QUEUE, to_ack)

if spy_tmp_file_name is not None:
    os.remove(spy_tmp_file_name)