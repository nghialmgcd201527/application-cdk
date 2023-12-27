import yaml
from yaml.loader import SafeLoader

class Config:
    # use the same name of each enviroment
    _environment = 'dev'
    data = []

    def __init__(self, environment) -> None:
        self._environment = environment
        self.load()

    def load(self) -> dict:
        with open(f'config/{self._environment}.yml') as f:
            self.data = yaml.load(f, Loader=SafeLoader)
        return self.data

    def get(self, key):
        return self.data[key]