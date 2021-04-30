import json

import h5py
import numpy as np
import pkg_resources
from numpy import ndarray
from tensorflow.keras import models
from tensorflow.keras.models import Model

from ..data_generation import MultilayerStructure


class TrainedModel:
    def __init__(self):
        self._sample = None
        self._keras_model = None
        self._q_values = None
        self._ip_mean = None
        self._ip_std = None

    def from_variable(self, model: Model, sample: MultilayerStructure, q_values: ndarray, ip_mean: ndarray,
                      ip_std: ndarray):
        self._sample = sample
        self._keras_model = model
        self._q_values = q_values
        self._ip_mean = ip_mean
        self._ip_std = ip_std

    def from_file(self, file_name: str):
        self._keras_model = models.load_model(file_name)
        sample = MultilayerStructure()
        with h5py.File(file_name, 'r') as model_file:
            sample_dict = json.loads(model_file['prediction_params/sample'][()])
            sample.from_dict(sample_dict)
            self._sample = sample
            self._q_values = np.array(model_file['prediction_params/q_values'])
            self._ip_mean = np.array(model_file['prediction_params/ip_mean'])
            self._ip_std = np.array(model_file['prediction_params/ip_std'])

    def save_model(self, file_name: str):
        models.save_model(self._keras_model, file_name)
        sample_json = json.dumps(self._sample.to_dict())
        with h5py.File(file_name, 'a') as model_file:
            prediction_params = model_file.create_group('prediction_params')
            prediction_params.create_dataset('sample', data=sample_json)
            prediction_params.create_dataset('q_values', data=self.q_values)
            prediction_params.create_dataset('ip_mean', data=self.ip_mean)
            prediction_params.create_dataset('ip_std', data=self.ip_std)

    @property
    def keras_model(self):
        return self._keras_model

    @property
    def q_values(self):
        return self._q_values

    @property
    def ip_mean(self):
        return self._ip_mean

    @property
    def ip_std(self):
        return self._ip_std

    @property
    def sample(self):
        return self._sample

    def _load_ip_values(self, ip_values_path: str):
        ip_values = np.loadtxt(ip_values_path)
        self._ip_mean = ip_values[:, 0]
        self._ip_std = ip_values[:, 1]


class DefaultTrainedModel(TrainedModel):
    def __init__(self):
        super().__init__()
        self.from_file(pkg_resources.resource_filename(__name__, 'default_trained_model.h5'))
