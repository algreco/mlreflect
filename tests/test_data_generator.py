import unittest

import numpy as np
from numpy import ndarray
from pandas import DataFrame

from mlreflect import Layer, MultilayerStructure
from mlreflect import ReflectivityGenerator


class TestReflectivityGeneratorMethods(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.layer1 = Layer('first_layer', (0, 100), (1, 10), (10, 20))
        cls.layer2 = Layer('second_layer', (50, 150), (1, 1), (-10, 10))

        cls.multilayer = MultilayerStructure((1, 5))
        cls.multilayer.add_layer(cls.layer1)
        cls.multilayer.add_layer(cls.layer2)

        cls.q = np.linspace(0.01, 0.14, 100)
        cls.generator = ReflectivityGenerator(cls.q, cls.multilayer)

        cls.labels = cls.generator.generate_random_labels(10)
        cls.reflectivity = cls.generator.simulate_reflectivity(cls.labels)

    def test_label_type(self):
        self.assertIsInstance(self.labels, DataFrame)

    def test_label_names(self):
        column_names = self.labels.columns
        self.assertEqual(column_names[0], 'second_layer_thickness')
        self.assertEqual(column_names[1], 'first_layer_roughness')
        self.assertEqual(column_names[2], 'second_layer_roughness')
        self.assertEqual(column_names[3], 'first_layer_sld')
        self.assertEqual(column_names[4], 'second_layer_sld')
        self.assertEqual(column_names[5], 'ambient_sld')

    def test_label_limits(self):
        self.assertTrue(np.max(self.labels['second_layer_thickness']) <= 150)
        self.assertTrue(np.min(self.labels['second_layer_thickness']) >= 50)

        self.assertTrue(np.max(self.labels['first_layer_roughness']) <= 10)
        self.assertTrue(np.min(self.labels['first_layer_roughness']) >= 1)

        self.assertTrue((self.labels['second_layer_roughness'] == 1).all())

        self.assertTrue(np.max(self.labels['first_layer_sld']) <= 20)
        self.assertTrue(np.min(self.labels['first_layer_sld']) >= 10)

        self.assertTrue(np.max(self.labels['second_layer_sld']) <= 10)
        self.assertTrue(np.min(self.labels['second_layer_sld']) >= -10)

        self.assertTrue(np.max(self.labels['ambient_sld']) <= 5)
        self.assertTrue(np.min(self.labels['ambient_sld']) >= 1)

    def test_reflectivity_type(self):
        self.assertIsInstance(self.reflectivity, ndarray)


if __name__ == '__main__':
    unittest.main()
