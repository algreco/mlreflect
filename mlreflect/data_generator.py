from typing import Tuple, List

import h5py
import numpy as np
from numpy import ndarray
from tqdm import tqdm

from mlreflect import multilayer_reflectivity as refl
from mlreflect.performance_tools import timer


class TrainingData:
    """Generation of simulated reflectivity data and labels for neural network training.

    Args:
        q_values: An array-like object (list, tuple, ndarray, etc.) that contains the q-values in units of
            1/Å at which the reflected intensity will be simulated.
        thickness_limits: An array-like object (list, tuple, ndarray, etc.) that contains a tuple with the min and max
            thickness in units of Å for each sample layer in order from top to bottom. The thickness of the bottom most
            layer (substrate) is not relevant for the simulation, but some value must be provided, e.g. (1, 1).
        roughness_limits: An array-like object (list, tuple, ndarray, etc.) that contains a tuple with the min and max
            roughness in units of Å for each sample interface in order from top (ambient/top layer) to bottom (bottom
            layer/substrate).
        sld_limits: An array-like object (list, tuple, ndarray, etc.) that contains a tuple with the min and max
            scattering length density (SLD) in units of 1e+14 1/Å^2 for each sample layer in order from top to bottom
            (excluding the ambient SLD).
        ambient_sld: Scattering length density of the ambient environment above the top most layer in units of 1e+14
            1/Å^2, e.g. ~0 for air.
        num_train: Number of training curves that will be simulated.
        num_val: Number of validation curves that will be simulated.
        num_test: Number of test curves that will be simulated.
        random_seed: Random seed for numpy.random.seed which affects the generation of the random labels.

    Methods:
        generate_data()

    Returns:
        TrainingData object.
    """

    def __init__(self, q_values: ndarray, thickness_limits: List[Tuple[float, float]], roughness_limits: List[Tuple[
        float, float]], sld_limits: List[Tuple[float, float]], ambient_sld: float, num_train: int, num_val: int,
                 num_test: int, random_seed: int = 1):

        np.random.seed(random_seed)
        self.q_values = np.asarray(q_values)
        self.thickness = np.asarray(thickness_limits)
        self.roughness = np.asarray(roughness_limits)
        self.sld = np.asarray(sld_limits)
        self.ambient_sld = ambient_sld

        self._number_of_layers = len(self.thickness)

        if num_train < 1 or num_val < 1:
            raise ValueError('Number of training and validation curves must be at least 1.')

        self.number_of_training_curves = num_train
        self.number_of_validation_curves = num_val
        self.number_of_test_curves = num_test

        self.training_labels = None
        self.training_reflectivity = None
        self.validation_labels = None
        self.validation_reflectivity = None
        self.test_labels = None
        self.test_reflectivity = None

        self.bolster_fraction = 0.15
        self.bolster_width = 0.1

        self.q_noise_spread = 0
        self.shot_noise_spread = 0
        self.background_noise_base_level = 0
        self.background_noise_spread = 0
        self.slit_width = 0

    @timer
    def generate_data(self):
        """Generates labels and simulates reflectivity curves according to the given parameters and stores them in:
            `training_labels`
            `training_reflectivity`
            `validation_labels`
            `validation_reflectivity`
            `test_labels`
            `test_reflectivity`"""

        self.training_labels = self._generate_labels(self.number_of_training_curves)
        self.training_reflectivity = self._generate_reflectivity_curves(self.training_labels,
                                                                        self.number_of_training_curves)

        self.validation_labels = self._generate_labels(self.number_of_validation_curves)
        self.validation_reflectivity = self._generate_reflectivity_curves(self.validation_labels,
                                                                          self.number_of_validation_curves)

        self.test_labels = self._generate_labels(self.number_of_test_curves)
        self.test_reflectivity = self._generate_reflectivity_curves(self.test_labels, self.number_of_test_curves)

    def _generate_reflectivity_curves(self, labels: ndarray, number_of_curves: int):
        thicknesses = labels[:, :self._number_of_layers]
        roughnesses = labels[:, self._number_of_layers:2 * self._number_of_layers]
        slds = labels[:, 2 * self._number_of_layers:3 * self._number_of_layers]

        thicknesses_si = thicknesses * 1e-10
        roughnesses_si = roughnesses * 1e-10
        slds_si = slds * 1e14
        ambient_sld_si = self.ambient_sld * 1e14

        q_values_si = self.q_values * 1e10

        reflectivity_curves = np.zeros([number_of_curves, len(q_values_si)])

        noisy_q_values = self._make_noisy_q_values(q_values_si, number_of_curves)

        for curve in tqdm(range(number_of_curves)):
            reflectivity = refl(noisy_q_values[curve, :], thicknesses_si[curve, :], roughnesses_si[curve, :],
                                slds_si[curve, :], ambient_sld_si)

            reflectivity_noisy = self._apply_shot_noise(reflectivity)
            reflectivity_noisy = self._apply_background_noise(reflectivity_noisy)

            convoluted_reflectivity = self._apply_slit_convolution(q_values_si, reflectivity_noisy)

            reflectivity_curves[curve, :] = convoluted_reflectivity

        return reflectivity_curves

    def _make_noisy_q_values(self, q_values: ndarray, number_of_curves: int):
        percentage_deviation = np.random.normal(1, self.q_noise_spread, (number_of_curves, len(q_values)))
        return q_values * percentage_deviation

    def _apply_shot_noise(self, reflectivity_curve: ndarray):
        noisy_reflectivity = np.clip(np.random.normal(reflectivity_curve, self.shot_noise_spread * np.sqrt(
            reflectivity_curve)), 1e-8, None)

        return noisy_reflectivity

    def _apply_background_noise(self, reflectivity_curve: ndarray):
        num_q_values = len(reflectivity_curve)
        background = np.random.normal(self.background_noise_base_level, self.background_noise_spread, num_q_values)

        return reflectivity_curve + background

    # TODO This method is not yet finished and should only be used with slit_width = 0.
    def _apply_slit_convolution(self, q_values: ndarray, reflectivity_curve: ndarray):
        sigma = self.slit_width
        if sigma == 0:
            return reflectivity_curve

        conv_reflectivity = np.zeros_like(reflectivity_curve)
        q_values /= np.max(q_values)
        for i in range(len(conv_reflectivity)):
            q_pos = q_values[i]
            g = self._gauss(q_values, sigma, q_pos)
            g_norm = g / sum(g)

            weighted_reflectivity = g_norm * reflectivity_curve
            conv_reflectivity[i] = sum(weighted_reflectivity)
        return conv_reflectivity

    @staticmethod
    def _gauss(x, sigma: float = 1.0, mu: float = 0.0):
        g = 1 / (2 * np.pi * sigma ** 2) * np.exp(-(x - mu) ** 2 / (2 * sigma ** 2))
        return g

    def _generate_labels(self, number_of_samples: int):
        randomized_slds = self._generate_random_values(self.sld, number_of_samples)
        randomized_thicknesses = self._generate_random_values(self.thickness, number_of_samples)
        randomized_roughnesses = self._generate_random_roughness_from_thickness(randomized_thicknesses)

        labels = np.concatenate((randomized_thicknesses, randomized_roughnesses, randomized_slds), axis=1)

        return labels

    def _generate_random_values(self, limits, number_of_values: int):
        randomized_labels = np.zeros((number_of_values, self._number_of_layers))
        for layer_index in range(self._number_of_layers):
            limits_layer = limits[layer_index]

            if np.all(np.isreal(limits_layer)):
                randomized_labels[:, layer_index] = self._bolstered_uniform_distribution(*limits_layer,
                                                                                         number_of_values)
            else:
                real_randomized_labels = self._generate_random_values(limits_layer[0].real, number_of_values)
                imag_randomized_labels = self._generate_random_values(limits_layer[1].imag, number_of_values)
                randomized_labels[:, layer_index] = real_randomized_labels + 1j * imag_randomized_labels

        return randomized_labels

    def _bolstered_uniform_distribution(self, value_min: float, value_max: float, n_samples: int):
        span = value_max - value_min

        n_bolster = int(np.ceil(n_samples * self.bolster_fraction / 2))
        n_uniform = n_samples - 2 * n_bolster

        uniform = np.random.uniform(value_min, value_max, n_uniform)

        bolster_min = np.random.normal(value_min, span * self.bolster_width, n_bolster)
        bolster_min = self._fold_distribution(bolster_min, value_min, value_max)
        bolster_max = np.random.normal(value_max, span * self.bolster_width, n_bolster)
        bolster_max = self._fold_distribution(bolster_max, value_min, value_max)

        total_distribution = np.concatenate((bolster_min, uniform, bolster_max))
        np.random.shuffle(total_distribution)

        return total_distribution

    @staticmethod
    def _fold_distribution(values: ndarray, min_value: float, max_value: float):
        num_values = len(values)
        for i in range(num_values):
            if values[i] < min_value:
                values[i] += 2 * (min_value - values[i])
            elif values[i] > max_value:
                values[i] += 2 * (max_value - values[i])
        return values

    def _generate_random_roughness_from_thickness(self, randomized_thicknesses: ndarray):
        randomized_roughnesses = np.zeros_like(randomized_thicknesses)
        number_of_samples = randomized_thicknesses.shape[0]

        min_roughnesses = self.roughness[:, 0]
        max_roughnesses = self.roughness[:, 1]

        for sample in range(number_of_samples):
            for layer in range(self._number_of_layers):
                max_roughness_from_thickness = self._thickness_correlation(randomized_thicknesses[sample, layer])
                if max_roughness_from_thickness < min_roughnesses[layer]:
                    randomized_roughnesses[sample, layer] = min_roughnesses[layer]
                elif max_roughness_from_thickness > max_roughnesses[layer]:
                    randomized_roughnesses[sample, layer] = np.random.uniform(min_roughnesses[layer],
                                                                              max_roughnesses[layer])
                else:
                    randomized_roughnesses[sample, layer] = np.random.uniform(min_roughnesses[layer],
                                                                              max_roughness_from_thickness)
        return randomized_roughnesses

    @staticmethod
    def _thickness_correlation(thickness: float):
        roughness = thickness / 2
        return roughness

    def save_data_as_h5(self, file_name: str):
        """Saves the generated data plus additional information in the .5h file `file_name`."""
        if self.training_reflectivity is None:
            raise AttributeError('No data generated yet. Generate data first.')

        if not (file_name.endswith('.h5') or file_name.endswith('.hdf5')):
            file_name += '.h5'

        with h5py.File(file_name, 'w') as data_file:
            data_file.attrs['q_unit'] = '1/A'
            data_file.create_dataset('q_values', data=self.q_values)

            data_file.attrs['number_of_layers'] = self._number_of_layers

            data_file.create_dataset('thickness_ranges', data=self.thickness)
            data_file.create_dataset('roughness_ranges', data=self.roughness)
            data_file.create_dataset('SLD_ranges', data=self.sld)

            data_file.attrs['num_curves_train'] = self.number_of_training_curves
            data_file.attrs['num_curves_val'] = self.number_of_validation_curves
            data_file.attrs['num_curves_test'] = self.number_of_test_curves

            training = data_file.create_group('training')
            training.create_dataset('reflectivity', data=self.training_reflectivity)
            training.create_dataset('labels', data=self.training_labels)

            validation = data_file.create_group('validation')
            validation.create_dataset('reflectivity', data=self.validation_reflectivity)
            validation.create_dataset('labels', data=self.validation_labels)

            test = data_file.create_group('test')
            test.create_dataset('reflectivity', data=self.test_reflectivity)
            test.create_dataset('labels', data=self.test_labels)
