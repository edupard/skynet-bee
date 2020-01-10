from google.cloud import datastore

class SamplesRepo:
    def __init__(self):
        self.db = datastore.Client('skynet-1984')

    def create(self, batch_id, ticker, i_date):
        entity = datastore.Entity(key=self.db.key('samples'))
        entity['batch_id'] = batch_id
        entity['ticker'] = ticker
        entity['date'] = i_date
        self.db.put(entity)

    def get(self, ticker):
        query = self.db.query(kind='samples')
        query.add_filter('ticker', '=', ticker)
        return list(query.fetch())

    def remove(self, batch_id):
        query = self.db.query(kind='samples')
        query.add_filter('batch_id', '=', batch_id)
        query.keys_only()
        entities = list(query.fetch())
        keys = list(map(lambda e: e.key, entities))
        self.db.delete_multi(keys)