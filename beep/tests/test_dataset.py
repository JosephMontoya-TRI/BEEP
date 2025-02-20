# Copyright [2020] [Toyota Research Institute]
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Unit tests related to dataset generation"""

import unittest
import os
from beep.featurize import (
    RPTdQdVFeatures,
    HPPCResistanceVoltageFeatures,
    DiagnosticSummaryStats,
    DiagnosticProperties
)
from beep import MODULE_DIR
from beep.dataset import BeepDataset, get_threshold_targets
from monty.tempfile import ScratchDir
from monty.serialization import dumpfn, loadfn
import shutil

TEST_DIR = os.path.dirname(__file__)
TEST_FILE_DIR = os.path.join(TEST_DIR, "test_files")
DIAGNOSTIC_PROCESSED = os.path.join(TEST_FILE_DIR, "PreDiag_000240_000227_truncated_structure.json")
FASTCHARGE_PROCESSED = os.path.join(TEST_FILE_DIR, '2017-06-30_2C-10per_6C_CH10_structure.json')

BIG_FILE_TESTS = os.environ.get("BEEP_BIG_TESTS", False)
SKIP_MSG = "Tests requiring large files with diagnostic cycles are disabled, set BIG_FILE_TESTS to run full tests"
FEATURIZER_CLASSES = [RPTdQdVFeatures, HPPCResistanceVoltageFeatures, DiagnosticSummaryStats]
FEATURE_HYPERPARAMS = loadfn(
    os.path.join(MODULE_DIR, "features/feature_hyperparameters.yaml")
)

class TestDataset(unittest.TestCase):
    def setUp(self):
        pass

    def test_from_features(self):
        dataset = BeepDataset.from_features('test_dataset', ['PreDiag'], FEATURIZER_CLASSES,
                                            feature_dir=os.path.join(TEST_FILE_DIR, 'data-share/features'))
        self.assertEqual(dataset.name, 'test_dataset')
        self.assertEqual(dataset.data.shape, (2, 56))
        #from pdb import set_trace; set_trace()
        self.assertListEqual(list(dataset.data.seq_num), [196, 197])
        self.assertIsNone(dataset.X_test)
        self.assertSetEqual(set(dataset.feature_sets.keys()), {'RPTdQdVFeatures', 'DiagnosticSummaryStats'})
        self.assertEqual(dataset.missing.feature_class.iloc[0], 'HPPCResistanceVoltageFeatures')

    def test_serialization(self):
        with ScratchDir("."):
            os.environ["BEEP_PROCESSING_DIR"] = os.getcwd()
            dataset = BeepDataset.from_features('test_dataset', ['PreDiag'], FEATURIZER_CLASSES,
                                            feature_dir=os.path.join(TEST_FILE_DIR, 'data-share/features'))
            dumpfn(dataset, 'temp_dataset.json')
            dataset = loadfn('temp_dataset.json')
            self.assertEqual(dataset.name, 'test_dataset')
            self.assertEqual(dataset.data.shape, (2, 56))
            # from pdb import set_trace; set_trace()
            self.assertListEqual(list(dataset.data.seq_num), [196, 197])
            self.assertIsNone(dataset.X_test)
            self.assertSetEqual(set(dataset.feature_sets.keys()), {'RPTdQdVFeatures', 'DiagnosticSummaryStats'})
            self.assertEqual(dataset.missing.feature_class.iloc[0], 'HPPCResistanceVoltageFeatures')
            self.assertIsInstance(dataset.filenames, list)

            os.environ["BEEP_PROCESSING_DIR"] = os.getcwd()
            dataset2 = BeepDataset.from_features('test_dataset', ['PreDiag'], [RPTdQdVFeatures],
                                                feature_dir=os.path.join(TEST_FILE_DIR, 'data-share/features'))
            dumpfn(dataset2, "temp_dataset_2.json")
            dataset2 = loadfn('temp_dataset_2.json')
            self.assertEqual(dataset2.missing.columns.to_list(), ["filename", "feature_class"])

    def test_from_processed_cycler_run_list(self):
        with ScratchDir("."):
            os.environ["BEEP_PROCESSING_DIR"] = os.getcwd()
            os.makedirs(os.path.join(os.getcwd(), "data-share", "raw", "parameters"))
            parameter_files = os.listdir(os.path.join(TEST_FILE_DIR, "data-share", "raw", "parameters"))
            for file in parameter_files:
                shutil.copy(os.path.join(TEST_FILE_DIR, "data-share", "raw", "parameters", file),
                            os.path.join(os.getcwd(), "data-share", "raw", "parameters"))
            dataset = BeepDataset.from_processed_cycler_runs('test_dataset',
                                                             project_list=None,
                                                             processed_run_list=[DIAGNOSTIC_PROCESSED,
                                                                                 FASTCHARGE_PROCESSED],
                                                             feature_class_list=FEATURIZER_CLASSES,
                                                             processed_dir=TEST_FILE_DIR,
                                                             feature_dir='data-share/features')
            self.assertEqual(dataset.name, 'test_dataset')
            self.assertEqual(dataset.data.shape, (1, 143))
            self.assertEqual(dataset.data.seq_num.iloc[0], 240)
            self.assertIsNone(dataset.X_test)

            self.assertEqual(dataset.missing.shape, (3, 2))
            self.assertEqual(dataset.missing.filename.iloc[0],
                             os.path.split(FASTCHARGE_PROCESSED)[1])

    def test_dataset_with_custom_feature_hyperparameters(self):
        with ScratchDir("."):
            os.environ["BEEP_PROCESSING_DIR"] = os.getcwd()
            os.makedirs(os.path.join(os.getcwd(), "data-share", "raw", "parameters"))
            parameter_files = os.listdir(os.path.join(TEST_FILE_DIR, "data-share", "raw", "parameters"))
            for file in parameter_files:
                shutil.copy(os.path.join(TEST_FILE_DIR, "data-share", "raw", "parameters", file),
                            os.path.join(os.getcwd(), "data-share", "raw", "parameters"))
            hyperparameter_dict = {'RPTdQdVFeatures': [
                {'test_time_filter_sec': 1000000, 'cycle_index_filter': 6,
                 'diag_ref': 0, 'diag_nr': 1, 'charge_y_n': 0, 'rpt_type': 'rpt_0.2C', 'plotting_y_n': 0},
                {'test_time_filter_sec': 1000000, 'cycle_index_filter': 6,
                 'diag_ref': 0, 'diag_nr': 1, 'charge_y_n': 0, 'rpt_type': 'rpt_1C', 'plotting_y_n': 0},
                {'test_time_filter_sec': 1000000, 'cycle_index_filter': 6,
                 'diag_ref': 0, 'diag_nr': 1, 'charge_y_n': 0, 'rpt_type': 'rpt_2C', 'plotting_y_n': 0}],
                                   'HPPCResistanceVoltageFeatures': [
                                       FEATURE_HYPERPARAMS['HPPCResistanceVoltageFeatures']],
                                   'DiagnosticSummaryStats': [FEATURE_HYPERPARAMS['DiagnosticSummaryStats']]
                                   }
            dataset = BeepDataset.from_processed_cycler_runs('test_dataset',
                                                             project_list=None,
                                                             processed_run_list=[DIAGNOSTIC_PROCESSED,
                                                                                 FASTCHARGE_PROCESSED],
                                                             feature_class_list=FEATURIZER_CLASSES,
                                                             processed_dir=TEST_FILE_DIR,
                                                             hyperparameter_dict=hyperparameter_dict,
                                                             feature_dir='data-share/features')
            self.assertEqual(dataset.name, 'test_dataset')
            self.assertEqual(dataset.data.shape, (1, 159))
            self.assertEqual(dataset.data.seq_num.iloc[0], 240)
            self.assertIsNone(dataset.X_test)

            self.assertEqual(dataset.missing.shape, (5, 2))
            self.assertEqual(dataset.missing.filename.iloc[0],
                             os.path.split(FASTCHARGE_PROCESSED)[1])

    def test_train_test_split(self):
        dataset = BeepDataset.from_features('test_dataset', ['PreDiag'], FEATURIZER_CLASSES,
                                            feature_dir=os.path.join(TEST_FILE_DIR, 'data-share', 'features'))
        predictors = dataset.feature_sets['RPTdQdVFeatures'][0:3] + \
                     dataset.feature_sets['DiagnosticSummaryStats'][-3:]

        X_train, X_test, y_train, y_test = \
            dataset.generate_train_test_split(predictors=predictors,
                                              outcomes=dataset.feature_sets['RPTdQdVFeatures'][-1],
                                              test_size=0.5, seed=123,
                                              parameters_path=os.path.join(TEST_FILE_DIR,
                                                                           'data-share',
                                                                           'raw',
                                                                           'parameters'))

        self.assertEqual(dataset.data.shape, (2, 56))
        self.assertEqual(dataset.X_test.shape, (1, 6))
        self.assertEqual(dataset.X_train.shape, (1, 6))

        parameter_dict = {'PreDiag_000197':
                              {'project_name': 'PreDiag',
                               'seq_num': 197,
                               'template': 'diagnosticV3.000',
                               'charge_constant_current_1': 0.2,
                               'charge_percent_limit_1': 30,
                               'charge_constant_current_2': 0.2,
                               'charge_cutoff_voltage': 3.7,
                               'charge_constant_voltage_time': 30,
                               'charge_rest_time': 5, 'discharge_constant_current': 0.2,
                               'discharge_cutoff_voltage': 3.5, 'discharge_rest_time': 15,
                               'cell_temperature_nominal': 25, 'cell_type': 'Tesla_Model3_21700',
                               'capacity_nominal': 4.84, 'diagnostic_type': 'HPPC+RPT',
                               'diagnostic_parameter_set': 'Tesla21700',
                               'diagnostic_start_cycle': 30,
                               'diagnostic_interval': 100}
                          }

        self.assertDictEqual(dataset.train_cells_parameter_dict, parameter_dict)

    def test_get_threshold_targets(self):
        dataset_diagnostic_properties = loadfn(os.path.join(TEST_FILE_DIR, "diagnostic_properties_test.json"))
        threshold_targets_df = get_threshold_targets(dataset_diagnostic_properties.data,
                                                     cycle_type="rpt_1C")
        self.assertEqual(len(threshold_targets_df), 92)
        self.assertEqual(threshold_targets_df.columns.to_list(), ['file',
                                                                  'seq_num',
                                                                  'initial_regular_throughput',
                                                                  'rpt_1Cdischarge_energy0.8_normalized_reg_throughput',
                                                                  'rpt_1Cdischarge_energy0.8_real_reg_throughput',
                                                                  'rpt_1Cdischarge_energy0.8_cycles']
                         )
        self.assertEqual(threshold_targets_df[threshold_targets_df['seq_num'] == 154].round(decimals=3).to_dict("list"),
                         {
                             'file': ['PredictionDiagnostics_000154'],
                             'seq_num': [154],
                             'initial_regular_throughput': [489.31],
                             'rpt_1Cdischarge_energy0.8_normalized_reg_throughput': [4.453],
                             'rpt_1Cdischarge_energy0.8_real_reg_throughput': [2178.925],
                             'rpt_1Cdischarge_energy0.8_cycles': [159.766]
                          }
                         )
        threshold_targets_df = get_threshold_targets(dataset_diagnostic_properties.data,
                                                     cycle_type="rpt_1C",
                                                     extrapolate_threshold=False)
        self.assertEqual(len(threshold_targets_df), 64)
        self.assertEqual(threshold_targets_df['rpt_1Cdischarge_energy0.8_real_reg_throughput'].round(decimals=3)
                         .median(), 2016.976)
