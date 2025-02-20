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
"""Unit tests related to cycler run data structures"""

import json
import os
import subprocess
import tempfile
import unittest
import numpy as np
import pandas as pd

from pathlib import Path
from beep import MODULE_DIR
from beep.structure import (
    RawCyclerRun,
    ProcessedCyclerRun,
    process_file_list_from_json,
    EISpectrum,
    determine_whether_step_is_waveform_discharge,
    determine_whether_step_is_waveform_charge,
    get_max_paused_over_threshold
)
from beep.utils import parameters_lookup
from beep.conversion_schemas import STRUCTURE_DTYPES
from monty.serialization import loadfn, dumpfn
from monty.tempfile import ScratchDir
from beep.utils import os_format
from beep.utils.s3 import download_s3_object
import matplotlib.pyplot as plt

BIG_FILE_TESTS = os.environ.get("BIG_FILE_TESTS", None) == "True"
SKIP_MSG = "Tests requiring large files with diagnostic cycles are disabled, set BIG_FILE_TESTS=True to run full tests"
TEST_DIR = os.path.dirname(__file__)
TEST_FILE_DIR = os.path.join(TEST_DIR, "test_files")


class RawCyclerRunTest(unittest.TestCase):
    def setUp(self):
        self.arbin_bad = os.path.join(
            TEST_FILE_DIR, "2017-05-09_test-TC-contact_CH33.csv"
        )
        self.arbin_file = os.path.join(
            TEST_FILE_DIR, "2017-12-04_4_65C-69per_6C_CH29.csv"
        )
        self.maccor_file = os.path.join(TEST_FILE_DIR, "xTESLADIAG_000019_CH70.070")
        self.maccor_file_w_diagnostics = os.path.join(
            TEST_FILE_DIR, "xTESLADIAG_000020_CH71.071"
        )
        self.maccor_file_w_waveform = os.path.join(TEST_FILE_DIR, "test_drive_071620.095")

        self.maccor_file_w_parameters_s3 = {
            "bucket": "beep-sync-test-stage",
            "key": "big_file_tests/PreDiag_000287_000128.092"
        }
        self.maccor_file_w_parameters = os.path.join(
            TEST_FILE_DIR, "PreDiag_000287_000128.092"
        )
        self.maccor_file_diagnostic_normal = os.path.join(
            TEST_FILE_DIR, "PreDiag_000287_000128short.092"
        )
        self.maccor_file_diagnostic_misplaced = os.path.join(
            TEST_FILE_DIR, "PreDiag_000412_00008Fshort.022"
        )
        self.maccor_file_timezone = os.path.join(
            TEST_FILE_DIR, "PredictionDiagnostics_000109_tztest.010"
        )
        self.maccor_file_timestamp = os.path.join(
            TEST_FILE_DIR, "PredictionDiagnostics_000151_test.052"
        )
        self.maccor_file_paused = os.path.join(
            TEST_FILE_DIR, "PredictionDiagnostics_000151_paused.052"
        )
        self.indigo_file = os.path.join(TEST_FILE_DIR, "indigo_test_sample.h5")
        self.neware_file = os.path.join(TEST_FILE_DIR, "raw", "neware_test.csv")
        self.biologic_file = os.path.join(
            TEST_FILE_DIR, "raw", "biologic_test_file_short.mpt"
        )

    def test_serialization(self):
        smaller_run = RawCyclerRun.from_file(self.arbin_bad)
        with ScratchDir("."):
            dumpfn(smaller_run, "smaller_cycler_run.json")
            resurrected = loadfn("smaller_cycler_run.json")
            self.assertIsInstance(resurrected, RawCyclerRun)
            self.assertIsInstance(resurrected.data, pd.DataFrame)
            self.assertEqual(
                smaller_run.data.voltage.to_list(), resurrected.data.voltage.to_list()
            )
            self.assertEqual(
                smaller_run.data.current.to_list(), resurrected.data.current.to_list()
            )

    def test_ingestion_maccor(self):
        raw_cycler_run = RawCyclerRun.from_maccor_file(
            self.maccor_file, include_eis=False
        )
        # Simple test of whether or not correct number of columns is parsed for data/metadata
        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            {
                "barcode",
                "_today_datetime",
                "start_datetime",
                "filename",
                "protocol",
                "channel_id",
            },
        )
        self.assertEqual(70, raw_cycler_run.metadata["channel_id"])
        # self.assertIsNotNone(raw_cycler_run.eis)

        # Test filename recognition
        raw_cycler_run = RawCyclerRun.from_file(self.maccor_file)
        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            {
                "barcode",
                "_today_datetime",
                "start_datetime",
                "filename",
                "protocol",
                "channel_id",
            },
        )

        # Quick test to see whether columns get recasted
        self.assertTrue(
            {
                "data_point",
                "cycle_index",
                "step_index",
                "voltage",
                "temperature",
                "current",
                "charge_capacity",
                "discharge_capacity",
            }
            < set(raw_cycler_run.data.columns)
        )

    def test_timezone_maccor(self):
        raw_cycler_run = RawCyclerRun.from_maccor_file(
            self.maccor_file_timezone, include_eis=False
        )
        # Simple test of whether or not correct number of columns is parsed for data/metadata
        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            {
                "barcode",
                "_today_datetime",
                "start_datetime",
                "filename",
                "protocol",
                "channel_id",
            },
        )
        self.assertEqual(10, raw_cycler_run.metadata["channel_id"])
        # self.assertIsNotNone(raw_cycler_run.eis)

        # Test filename recognition
        raw_cycler_run = RawCyclerRun.from_file(self.maccor_file)
        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            {
                "barcode",
                "_today_datetime",
                "start_datetime",
                "filename",
                "protocol",
                "channel_id",
            },
        )

        # Quick test to see whether columns get recasted
        self.assertTrue(
            {
                "data_point",
                "cycle_index",
                "step_index",
                "voltage",
                "temperature",
                "current",
                "charge_capacity",
                "discharge_capacity",
            }
            < set(raw_cycler_run.data.columns)
        )

    def test_timestamp_maccor(self):
        raw_cycler_run = RawCyclerRun.from_maccor_file(
            self.maccor_file_timestamp, include_eis=False
        )
        # Simple test of whether or not correct number of columns is parsed for data/metadata
        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            {
                "barcode",
                "_today_datetime",
                "start_datetime",
                "filename",
                "protocol",
                "channel_id",
            },
        )
        # self.assertIsNotNone(raw_cycler_run.eis)

        # Test filename recognition
        raw_cycler_run = RawCyclerRun.from_file(self.maccor_file)
        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            {
                "barcode",
                "_today_datetime",
                "start_datetime",
                "filename",
                "protocol",
                "channel_id",
            },
        )

        # Quick test to see whether columns get recasted
        self.assertTrue(
            {
                "data_point",
                "cycle_index",
                "step_index",
                "voltage",
                "temperature",
                "current",
                "charge_capacity",
                "discharge_capacity",
            }
            < set(raw_cycler_run.data.columns)
        )

    def test_quantity_sum_maccor(self):
        raw_cycler_run = RawCyclerRun.from_maccor_file(
            self.maccor_file_w_diagnostics, include_eis=False
        )
        cycle_sign = np.sign(np.diff(raw_cycler_run.data["cycle_index"]))
        capacity_sign = np.sign(np.diff(raw_cycler_run.data["charge_capacity"]))
        self.assertTrue(
            np.all(capacity_sign >= -cycle_sign)
        )  # Capacity increases throughout cycle
        capacity_sign = np.sign(np.diff(raw_cycler_run.data["discharge_capacity"]))
        self.assertTrue(
            np.all(capacity_sign >= -cycle_sign)
        )  # Capacity increases throughout cycle

    def test_waveform_charge_discharge_capacity(self):
        raw_cycler_run = RawCyclerRun.from_maccor_file(
            self.maccor_file_w_waveform, include_eis=False
        )
        cycle_sign = np.sign(np.diff(raw_cycler_run.data["cycle_index"]))
        capacity_sign = np.sign(np.diff(raw_cycler_run.data["charge_capacity"]))
        self.assertTrue(
            np.all(capacity_sign >= -cycle_sign)
        )  # Capacity increases throughout cycle
        capacity_sign = np.sign(np.diff(raw_cycler_run.data["discharge_capacity"]))
        self.assertTrue(
            np.all(capacity_sign >= -cycle_sign)
        )

    # Note that the compression is from 45 M / 6 M as of 02/25/2019
    def test_binary_save(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        with ScratchDir("."):
            cycler_run.save_numpy_binary("test")
            loaded = cycler_run.load_numpy_binary("test")

        # Test equivalence of columns
        # More strict test
        self.assertTrue(
            np.all(
                loaded.data[RawCyclerRun.FLOAT_COLUMNS]
                == cycler_run.data[RawCyclerRun.FLOAT_COLUMNS]
            )
        )
        self.assertTrue(
            np.all(
                loaded.data[RawCyclerRun.INT_COLUMNS]
                == cycler_run.data[RawCyclerRun.INT_COLUMNS]
            )
        )

        # Looser test (for future size testing)
        self.assertTrue(
            np.allclose(
                loaded.data[RawCyclerRun.FLOAT_COLUMNS],
                cycler_run.data[RawCyclerRun.FLOAT_COLUMNS],
            )
        )
        self.assertTrue(
            np.all(
                loaded.data[RawCyclerRun.INT_COLUMNS]
                == cycler_run.data[RawCyclerRun.INT_COLUMNS]
            )
        )

    def test_get_interpolated_discharge_cycles(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        all_interpolated = cycler_run.get_interpolated_cycles()
        all_interpolated = all_interpolated[(all_interpolated.step_type == "discharge")]
        lengths = [len(df) for index, df in all_interpolated.groupby("cycle_index")]
        self.assertTrue(np.all(np.array(lengths) == 1000))

        # Found these manually
        all_interpolated = all_interpolated.drop(columns=["step_type"])
        y_at_point = all_interpolated.iloc[[1500]]
        x_at_point = all_interpolated.voltage[1500]
        cycle_1 = cycler_run.data[cycler_run.data["cycle_index"] == 1]

        # Discharge step is 12
        discharge = cycle_1[cycle_1.step_index == 12]
        discharge = discharge.sort_values("voltage")

        # Get an interval between which one can find the interpolated value
        measurement_index = np.max(np.where(discharge.voltage - x_at_point < 0))
        interval = discharge.iloc[measurement_index : measurement_index + 2]
        interval = interval.drop(columns=["date_time_iso"])  # Drop non-numeric column

        # Test interpolation with a by-hand calculation of slope
        diff = np.diff(interval, axis=0)
        pred = interval.iloc[[0]] + diff * (x_at_point - interval.voltage.iloc[0]) / (
            interval.voltage.iloc[1] - interval.voltage.iloc[0]
        )
        pred = pred.reset_index()
        for col_name in y_at_point.columns:
            self.assertAlmostEqual(
                pred[col_name].iloc[0], y_at_point[col_name].iloc[0], places=2
            )

    def test_get_interpolated_charge_step(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        reg_cycles = [i for i in cycler_run.data.cycle_index.unique()]
        v_range = [2.8, 3.5]
        resolution = 1000
        interpolated_charge = cycler_run.get_interpolated_steps(
            v_range,
            resolution,
            step_type="charge",
            reg_cycles=reg_cycles,
            axis="test_time",
        )
        lengths = [len(df) for index, df in interpolated_charge.groupby("cycle_index")]
        axis_1 = interpolated_charge[
            interpolated_charge.cycle_index == 5
        ].charge_capacity.to_list()
        axis_2 = interpolated_charge[
            interpolated_charge.cycle_index == 10
        ].charge_capacity.to_list()
        self.assertGreater(max(axis_1), max(axis_2))
        self.assertTrue(np.all(np.array(lengths) == 1000))
        self.assertTrue(interpolated_charge["current"].mean() > 0)

    def test_whether_step_is_waveform(self):
        cycler_run = RawCyclerRun.from_file(self.maccor_file_w_waveform)
        self.assertTrue(cycler_run.data.loc[cycler_run.data.cycle_index == 6].
                        groupby("step_index").apply(determine_whether_step_is_waveform_discharge).any())
        self.assertFalse(cycler_run.data.loc[cycler_run.data.cycle_index == 6].
                        groupby("step_index").apply(determine_whether_step_is_waveform_charge).any())
        self.assertFalse(cycler_run.data.loc[cycler_run.data.cycle_index == 3].
                        groupby("step_index").apply(determine_whether_step_is_waveform_discharge).any())

    def test_get_interpolated_waveform_discharge_cycles(self):
        cycler_run = RawCyclerRun.from_file(self.maccor_file_w_waveform)
        all_interpolated = cycler_run.get_interpolated_cycles()
        all_interpolated = all_interpolated[(all_interpolated.step_type == "discharge")]
        self.assertTrue(all_interpolated.columns[0] == 'test_time')
        subset_interpolated = all_interpolated[all_interpolated.cycle_index==6]
        self.assertEqual(subset_interpolated.test_time.min(),
                         cycler_run.data.loc[(cycler_run.data.cycle_index == 6) &
                                             (cycler_run.data.step_index == 33)].test_time.min())
        self.assertEqual(subset_interpolated[subset_interpolated.cycle_index == 6].shape[0], 1000)

    def test_get_interpolated_charge_cycles(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        all_interpolated = cycler_run.get_interpolated_cycles()
        all_interpolated = all_interpolated[(all_interpolated.step_type == "charge")]
        lengths = [len(df) for index, df in all_interpolated.groupby("cycle_index")]
        axis_1 = all_interpolated[
            all_interpolated.cycle_index == 5
        ].charge_capacity.to_list()
        axis_2 = all_interpolated[
            all_interpolated.cycle_index == 10
        ].charge_capacity.to_list()
        self.assertEqual(axis_1, axis_2)
        self.assertTrue(np.all(np.array(lengths) == 1000))
        self.assertTrue(all_interpolated["current"].mean() > 0)

    def test_interpolated_cycles_dtypes(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        all_interpolated = cycler_run.get_interpolated_cycles()
        cycles_interpolated_dtypes = all_interpolated.dtypes.tolist()
        cycles_interpolated_columns = all_interpolated.columns.tolist()
        cycles_interpolated_dtypes = [str(dtyp) for dtyp in cycles_interpolated_dtypes]
        for indx, col in enumerate(cycles_interpolated_columns):
            self.assertEqual(
                cycles_interpolated_dtypes[indx],
                STRUCTURE_DTYPES["cycles_interpolated"][col],
            )

        cycler_run = RawCyclerRun.from_maccor_file(
            self.maccor_file_w_diagnostics, include_eis=False
        )
        all_interpolated = cycler_run.get_interpolated_cycles()
        cycles_interpolated_dyptes = all_interpolated.dtypes.tolist()
        cycles_interpolated_columns = all_interpolated.columns.tolist()
        cycles_interpolated_dyptes = [str(dtyp) for dtyp in cycles_interpolated_dyptes]
        for indx, col in enumerate(cycles_interpolated_columns):
            self.assertEqual(
                cycles_interpolated_dyptes[indx],
                STRUCTURE_DTYPES["cycles_interpolated"][col],
            )

    def test_summary_dtypes(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        all_summary = cycler_run.get_summary()
        reg_dyptes = all_summary.dtypes.tolist()
        reg_columns = all_summary.columns.tolist()
        reg_dyptes = [str(dtyp) for dtyp in reg_dyptes]
        for indx, col in enumerate(reg_columns):
            self.assertEqual(reg_dyptes[indx], STRUCTURE_DTYPES["summary"][col])

        cycler_run = RawCyclerRun.from_maccor_file(
            self.maccor_file_w_diagnostics, include_eis=False
        )
        all_summary = cycler_run.get_summary()
        reg_dyptes = all_summary.dtypes.tolist()
        reg_columns = all_summary.columns.tolist()
        reg_dyptes = [str(dtyp) for dtyp in reg_dyptes]
        for indx, col in enumerate(reg_columns):
            self.assertEqual(reg_dyptes[indx], STRUCTURE_DTYPES["summary"][col])

    @unittest.skipUnless(BIG_FILE_TESTS, SKIP_MSG)
    def test_get_diagnostic(self):
        os.environ["BEEP_PROCESSING_DIR"] = TEST_FILE_DIR

        download_s3_object(bucket=self.maccor_file_w_parameters_s3["bucket"],
                           key=self.maccor_file_w_parameters_s3["key"],
                           destination_path=self.maccor_file_w_parameters)

        cycler_run = RawCyclerRun.from_file(self.maccor_file_w_parameters)

        (
            v_range,
            resolution,
            nominal_capacity,
            full_fast_charge,
            diagnostic_available,
        ) = cycler_run.determine_structuring_parameters()
        self.assertEqual(nominal_capacity, 4.84)
        # self.assertEqual(v_range, [2.7, 4.2]) # This is an older assertion, value changed when
        # different cell types were added

        self.assertEqual(v_range, [2.5, 4.2])
        self.assertEqual(
            diagnostic_available["cycle_type"],
            ["reset", "hppc", "rpt_0.2C", "rpt_1C", "rpt_2C"],
        )
        diag_summary = cycler_run.get_diagnostic_summary(diagnostic_available)

        reg_summary = cycler_run.get_summary(diagnostic_available)
        self.assertEqual(len(reg_summary.cycle_index.tolist()), 230)
        self.assertEqual(reg_summary.cycle_index.tolist()[:10],
                         [0, 6, 7, 8, 9, 10, 11, 12, 13, 14])

        # Check data types are being set correctly for diagnostic summary
        diag_dyptes = diag_summary.dtypes.tolist()
        diag_columns = diag_summary.columns.tolist()
        diag_dyptes = [str(dtyp) for dtyp in diag_dyptes]
        for indx, col in enumerate(diag_columns):
            self.assertEqual(
                diag_dyptes[indx], STRUCTURE_DTYPES["diagnostic_summary"][col]
            )

        self.assertEqual(
            diag_summary.cycle_index.tolist(),
            [1, 2, 3, 4, 5, 36, 37, 38, 39, 40, 141, 142, 143, 144, 145, 246, 247],
        )
        self.assertEqual(
            diag_summary.cycle_type.tolist(),
            [
                "reset",
                "hppc",
                "rpt_0.2C",
                "rpt_1C",
                "rpt_2C",
                "reset",
                "hppc",
                "rpt_0.2C",
                "rpt_1C",
                "rpt_2C",
                "reset",
                "hppc",
                "rpt_0.2C",
                "rpt_1C",
                "rpt_2C",
                "reset",
                "hppc",
            ],
        )
        self.assertEqual(diag_summary.paused.max(), 0)
        diag_interpolated = cycler_run.get_interpolated_diagnostic_cycles(
            diagnostic_available, resolution=1000
        )

        # Check data types are being set correctly for interpolated data
        diag_dyptes = diag_interpolated.dtypes.tolist()
        diag_columns = diag_interpolated.columns.tolist()
        diag_dyptes = [str(dtyp) for dtyp in diag_dyptes]
        for indx, col in enumerate(diag_columns):
            self.assertEqual(
                diag_dyptes[indx], STRUCTURE_DTYPES["diagnostic_interpolated"][col]
            )

        # Provide visual inspection to ensure that diagnostic interpolation is being done correctly
        diag_cycle = diag_interpolated[
            (diag_interpolated.cycle_type == "rpt_0.2C")
            & (diag_interpolated.step_type == 1)
        ]
        self.assertEqual(diag_cycle.cycle_index.unique().tolist(), [3, 38, 143])
        plt.figure()
        plt.plot(diag_cycle.discharge_capacity, diag_cycle.voltage)
        plt.savefig(os.path.join(TEST_FILE_DIR, "discharge_capacity_interpolation.png"))
        plt.figure()
        plt.plot(diag_cycle.voltage, diag_cycle.discharge_dQdV)
        plt.savefig(os.path.join(TEST_FILE_DIR, "discharge_dQdV_interpolation.png"))

        self.assertEqual(len(diag_cycle.index), 3000)

        hppcs = diag_interpolated[
            (diag_interpolated.cycle_type == "hppc")
            & pd.isnull(diag_interpolated.current)
        ]
        self.assertEqual(len(hppcs), 0)

        hppc_dischg1 = diag_interpolated[
            (diag_interpolated.cycle_index == 37)
            & (diag_interpolated.step_type == 2)
            & (diag_interpolated.step_index_counter == 3)
            & ~pd.isnull(diag_interpolated.current)
        ]

        plt.figure()
        plt.plot(hppc_dischg1.test_time, hppc_dischg1.voltage)
        plt.savefig(os.path.join(TEST_FILE_DIR, "hppc_discharge_pulse_1.png"))
        self.assertEqual(len(hppc_dischg1), 176)

        processed_cycler_run = cycler_run.to_processed_cycler_run()
        self.assertNotIn(
            diag_summary.cycle_index.tolist(),
            processed_cycler_run.cycles_interpolated.cycle_index.unique(),
        )
        self.assertEqual(
            reg_summary.cycle_index.tolist(),
            processed_cycler_run.summary.cycle_index.tolist(),
        )

        processed_cycler_run_loc = os.path.join(
            TEST_FILE_DIR, "processed_diagnostic.json"
        )
        # Dump to the structured file and check the file size
        dumpfn(processed_cycler_run, processed_cycler_run_loc)
        proc_size = os.path.getsize(processed_cycler_run_loc)
        self.assertLess(proc_size, 54000000)

        # Reload the structured file and check for errors
        test = loadfn(processed_cycler_run_loc)
        self.assertIsInstance(test.diagnostic_summary, pd.DataFrame)
        diag_dyptes = test.diagnostic_summary.dtypes.tolist()
        diag_columns = test.diagnostic_summary.columns.tolist()
        diag_dyptes = [str(dtyp) for dtyp in diag_dyptes]
        for indx, col in enumerate(diag_columns):
            self.assertEqual(
                diag_dyptes[indx], STRUCTURE_DTYPES["diagnostic_summary"][col]
            )

        diag_dyptes = test.diagnostic_interpolated.dtypes.tolist()
        diag_columns = test.diagnostic_interpolated.columns.tolist()
        diag_dyptes = [str(dtyp) for dtyp in diag_dyptes]
        for indx, col in enumerate(diag_columns):
            self.assertEqual(
                diag_dyptes[indx], STRUCTURE_DTYPES["diagnostic_interpolated"][col]
            )

        self.assertEqual(test.summary.cycle_index.tolist()[:10], [0, 6, 7, 8, 9, 10, 11, 12, 13, 14])

        plt.figure()
        single_charge = test.cycles_interpolated[
            (test.cycles_interpolated.step_type == "charge")
            & (test.cycles_interpolated.cycle_index == 25)
        ]
        self.assertEqual(len(single_charge.index), 1000)
        plt.plot(single_charge.charge_capacity, single_charge.voltage)
        plt.savefig(
            os.path.join(
                TEST_FILE_DIR, "charge_capacity_interpolation_regular_cycle.png"
            )
        )

        os.remove(processed_cycler_run_loc)

    def test_get_interpolated_cycles_maccor(self):
        cycler_run = RawCyclerRun.from_file(self.maccor_file)
        all_interpolated = cycler_run.get_interpolated_cycles(
            v_range=[3.0, 4.2], resolution=10000
        )

        self.assertSetEqual(set(all_interpolated.columns.tolist()),
                            {'voltage',
                             'test_time',
                             'discharge_capacity',
                             'discharge_energy',
                             'current',
                             'temperature',
                             'charge_capacity',
                             'charge_energy',
                             'internal_resistance',
                             'cycle_index',
                             'step_type'}
                            )
        interp2 = all_interpolated[
            (all_interpolated.cycle_index == 2)
            & (all_interpolated.step_type == "discharge")
        ].sort_values("discharge_capacity")
        interp3 = all_interpolated[
            (all_interpolated.cycle_index == 1)
            & (all_interpolated.step_type == "charge")
        ].sort_values("charge_capacity")

        self.assertTrue(interp3.current.mean() > 0)
        self.assertEqual(len(interp3.voltage), 10000)
        self.assertEqual(interp3.voltage.max(), np.float32(4.100838))
        self.assertEqual(interp3.voltage.min(), np.float32(3.3334765))
        np.testing.assert_almost_equal(
            interp3[
                interp3.charge_capacity <= interp3.charge_capacity.median()
            ].current.iloc[0],
            2.423209,
            decimal=6,
        )

        cycle_2 = cycler_run.data[cycler_run.data["cycle_index"] == 2]
        discharge = cycle_2[cycle_2.step_index == 12]
        discharge = discharge.sort_values("discharge_capacity")

        acceptable_error = 0.01
        acceptable_error_offest = 0.001
        voltages_to_check = [3.3, 3.2, 3.1]
        columns_to_check = [
            "voltage",
            "current",
            "discharge_capacity",
            "charge_capacity",
        ]
        for voltage_check in voltages_to_check:
            closest_interp2_index = interp2.index[
                (interp2["voltage"] - voltage_check).abs().min()
                == (interp2["voltage"] - voltage_check).abs()
            ]
            closest_interp2_match = interp2.loc[closest_interp2_index]
            print(closest_interp2_match)
            closest_discharge_index = discharge.index[
                (discharge["voltage"] - voltage_check).abs().min()
                == (discharge["voltage"] - voltage_check).abs()
            ]
            closest_discharge_match = discharge.loc[closest_discharge_index]
            print(closest_discharge_match)
            for column_check in columns_to_check:
                off_by = (
                    closest_interp2_match.iloc[0][column_check]
                    - closest_discharge_match.iloc[0][column_check]
                )
                print(column_check)
                print(np.abs(off_by))
                print(
                    np.abs(closest_interp2_match.iloc[0][column_check])
                    * acceptable_error
                )
                assert np.abs(off_by) <= (
                    np.abs(closest_interp2_match.iloc[0][column_check])
                    * acceptable_error
                    + acceptable_error_offest
                )

    def test_get_summary(self):
        cycler_run = RawCyclerRun.from_file(self.maccor_file_w_diagnostics)
        summary = cycler_run.get_summary(nominal_capacity=4.7, full_fast_charge=0.8)
        self.assertTrue(
            set.issubset(
                {
                    "discharge_capacity",
                    "charge_capacity",
                    "dc_internal_resistance",
                    "temperature_maximum",
                    "temperature_average",
                    "temperature_minimum",
                    "date_time_iso",
                    "charge_throughput",
                    "energy_throughput",
                    "charge_energy",
                    "discharge_energy",
                    "energy_efficiency",
                },
                set(summary.columns),
            )
        )
        self.assertEqual(summary["cycle_index"].tolist(), list(range(0, 13)))
        self.assertEqual(len(summary.index), len(summary["date_time_iso"]))
        self.assertEqual(summary["paused"].max(), 0)

    def test_get_energy(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        summary = cycler_run.get_summary(nominal_capacity=4.7, full_fast_charge=0.8)
        self.assertEqual(np.around(summary["charge_energy"][5], 6), np.around(3.7134638, 6))
        self.assertEqual(np.around(summary["energy_efficiency"][5], 7), np.around(np.float32(0.872866405753033), 7))

    def test_get_charge_throughput(self):
        cycler_run = RawCyclerRun.from_file(self.arbin_file)
        summary = cycler_run.get_summary(nominal_capacity=4.7, full_fast_charge=0.8)
        self.assertEqual(summary["charge_throughput"][5], np.float32(6.7614093))
        self.assertEqual(summary["energy_throughput"][5], np.float32(23.2752363))

    def test_ingestion_indigo(self):

        # specific
        raw_cycler_run = RawCyclerRun.from_indigo_file(self.indigo_file)
        self.assertTrue(
            {
                "data_point",
                "cycle_index",
                "step_index",
                "voltage",
                "temperature",
                "current",
                "charge_capacity",
                "discharge_capacity",
            }
            < set(raw_cycler_run.data.columns)
        )

        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            set({"indigo_cell_id", "_today_datetime", "start_datetime", "filename"}),
        )

        # general
        raw_cycler_run = RawCyclerRun.from_file(self.indigo_file)
        self.assertTrue(
            {
                "data_point",
                "cycle_index",
                "step_index",
                "voltage",
                "temperature",
                "current",
                "charge_capacity",
                "discharge_capacity",
            }
            < set(raw_cycler_run.data.columns)
        )

        self.assertEqual(
            set(raw_cycler_run.metadata.keys()),
            set({"indigo_cell_id", "_today_datetime", "start_datetime", "filename"}),
        )

    def test_ingestion_biologic(self):

        # specific
        raw_cycler_run = RawCyclerRun.from_biologic_file(self.biologic_file)

        self.assertEqual(
            {
                "cycle_index",
                "step_index",
                "voltage",
                "current",
                "discharge_capacity",
                "charge_capacity",
                "data_point",
                "charge_energy",
                "discharge_energy",
            },
            set(raw_cycler_run.data.columns),
        )

        self.assertEqual(
            set({"_today_datetime", "filename", "barcode", "protocol", "channel_id"}),
            set(raw_cycler_run.metadata.keys()),
        )

        # general
        raw_cycler_run = RawCyclerRun.from_file(self.biologic_file)

        self.assertEqual(
            {
                "cycle_index",
                "step_index",
                "voltage",
                "current",
                "discharge_capacity",
                "charge_capacity",
                "data_point",
                "charge_energy",
                "discharge_energy",
            },
            set(raw_cycler_run.data.columns),
        )

        self.assertEqual(
            set({"_today_datetime", "filename", "barcode", "protocol", "channel_id"}),
            set(raw_cycler_run.metadata.keys()),
        )

    def test_ingestion_neware(self):
        raw_cycler_run = RawCyclerRun.from_file(self.neware_file)
        self.assertEqual(raw_cycler_run.data.columns[22], "internal_resistance")
        self.assertTrue(raw_cycler_run.data["test_time"].is_monotonic_increasing)
        summary = raw_cycler_run.get_summary(nominal_capacity=4.7, full_fast_charge=0.8)
        self.assertEqual(summary["discharge_capacity"].head(5).round(4).tolist(),
                         [2.4393, 2.4343, 2.4255, 2.4221, 2.4210])
        self.assertEqual(summary[summary["cycle_index"] == 55]["discharge_capacity"].round(4).tolist(),
                         [2.3427])

    def test_get_project_name(self):
        project_name_parts = parameters_lookup.get_project_sequence(
            os.path.join(TEST_FILE_DIR, "PredictionDiagnostics_000109_tztest.010")
        )
        project_name = project_name_parts[0]
        self.assertEqual(project_name, "PredictionDiagnostics")

    def test_get_protocol_parameters(self):
        os.environ["BEEP_PROCESSING_DIR"] = TEST_FILE_DIR
        filepath = os.path.join(
            TEST_FILE_DIR, "PredictionDiagnostics_000109_tztest.010"
        )
        test_path = os.path.join("data-share", "raw", "parameters")
        parameters, _ = parameters_lookup.get_protocol_parameters(filepath, parameters_path=test_path)

        self.assertEqual(parameters["diagnostic_type"].iloc[0], "HPPC+RPT")
        self.assertEqual(parameters["diagnostic_parameter_set"].iloc[0], "Tesla21700")
        self.assertEqual(parameters["seq_num"].iloc[0], 109)
        self.assertEqual(len(parameters.index), 1)

        parameters_missing, project_missing = parameters_lookup.get_protocol_parameters(
            "Fake", parameters_path=test_path
        )
        self.assertEqual(parameters_missing, None)
        self.assertEqual(project_missing, None)

        filepath = os.path.join(TEST_FILE_DIR, "PreDiag_000292_tztest.010")
        parameters, _ = parameters_lookup.get_protocol_parameters(filepath, parameters_path=test_path)
        self.assertEqual(parameters["diagnostic_type"].iloc[0], "HPPC+RPT")
        self.assertEqual(parameters["seq_num"].iloc[0], 292)

    def test_determine_structuring_parameters(self):
        os.environ["BEEP_PROCESSING_DIR"] = TEST_FILE_DIR
        raw_cycler_run = RawCyclerRun.from_file(self.maccor_file_diagnostic_normal)
        (
            v_range,
            resolution,
            nominal_capacity,
            full_fast_charge,
            diagnostic_available,
        ) = raw_cycler_run.determine_structuring_parameters()
        diagnostic_available_test = {
            "parameter_set": "Tesla21700",
            "cycle_type": ["reset", "hppc", "rpt_0.2C", "rpt_1C", "rpt_2C"],
            "length": 5,
            "diagnostic_starts_at": [
                1, 36, 141, 246, 351, 456, 561, 666, 771, 876, 981, 1086, 1191,
                1296, 1401, 1506, 1611, 1716, 1821, 1926, 2031, 2136, 2241, 2346,
                2451, 2556, 2661, 2766, 2871, 2976, 3081, 3186, 3291, 3396, 3501,
                3606, 3628
            ]
        }
        self.assertEqual(v_range, [2.5, 4.2])
        self.assertEqual(resolution, 1000)
        self.assertEqual(nominal_capacity, 4.84)
        self.assertEqual(full_fast_charge, 0.8)
        self.assertEqual(diagnostic_available, diagnostic_available_test)

        raw_cycler_run = RawCyclerRun.from_file(self.maccor_file_diagnostic_misplaced)
        (
            v_range,
            resolution,
            nominal_capacity,
            full_fast_charge,
            diagnostic_available,
        ) = raw_cycler_run.determine_structuring_parameters()
        diagnostic_available_test = {
            "parameter_set": "Tesla21700",
            "cycle_type": ["reset", "hppc", "rpt_0.2C", "rpt_1C", "rpt_2C"],
            "length": 5,
            "diagnostic_starts_at": [1, 36, 141, 220, 255]
        }
        self.assertEqual(v_range, [2.5, 4.2])
        self.assertEqual(resolution, 1000)
        self.assertEqual(nominal_capacity, 4.84)
        self.assertEqual(full_fast_charge, 0.8)
        self.assertEqual(diagnostic_available, diagnostic_available_test)

    def test_get_diagnostic_parameters(self):
        os.environ["BEEP_PROCESSING_DIR"] = TEST_FILE_DIR
        diagnostic_available = {
            "parameter_set": "Tesla21700",
            "cycle_type": ["reset", "hppc", "rpt_0.2C", "rpt_1C", "rpt_2C"],
            "length": 5,
            "diagnostic_starts_at": [1, 36, 141],
        }
        diagnostic_parameter_path = os.path.join(MODULE_DIR, "procedure_templates")
        project_name = "PreDiag"
        v_range = parameters_lookup.get_diagnostic_parameters(
            diagnostic_available, diagnostic_parameter_path, project_name
        )
        self.assertEqual(v_range, [2.7, 4.2])

    def test_get_interpolated_diagnostic_cycles(self):
        cycler_run = RawCyclerRun.from_file(self.maccor_file_w_diagnostics)
        diagnostic_available = {
            "type": "HPPC",
            "cycle_type": ["hppc"],
            "length": 1,
            "diagnostic_starts_at": [1],
        }
        d_interp = cycler_run.get_interpolated_diagnostic_cycles(
            diagnostic_available, resolution=500
        )
        self.assertGreaterEqual(len(d_interp.cycle_index.unique()), 1)

        # Ensure step indices are partitioned and processed separately
        self.assertEqual(len(d_interp.step_index.unique()), 9)
        first_step = d_interp[
            (d_interp.step_index == 7) & (d_interp.step_index_counter == 1)
        ]
        second_step = d_interp[
            (d_interp.step_index == 7) & (d_interp.step_index_counter == 4)
        ]
        self.assertLess(first_step.voltage.diff().max(), 0.001)
        self.assertLess(second_step.voltage.diff().max(), 0.001)

    def test_get_diagnostic_summary(self):
        cycler_run = RawCyclerRun.from_file(self.maccor_file_w_diagnostics)
        diagnostic_available = {
            "type": "HPPC",
            "cycle_type": ["hppc"],
            "length": 1,
            "diagnostic_starts_at": [1],
        }
        diag_summary = cycler_run.get_diagnostic_summary(diagnostic_available)
        self.assertEqual(diag_summary["paused"].max(), 0)

    def test_determine_paused(self):
        cycler_run = RawCyclerRun.from_file(self.maccor_file_paused)
        paused = cycler_run.data.groupby("cycle_index").apply(get_max_paused_over_threshold)
        self.assertEqual(paused.max(), 7201.0)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.arbin_file = os.path.join(
            TEST_FILE_DIR, "2017-12-04_4_65C-69per_6C_CH29.csv"
        )

    def test_simple_conversion(self):
        with ScratchDir("."):
            # Set root env
            os.environ["BEEP_PROCESSING_DIR"] = os.getcwd()
            # Make necessary directories
            os.mkdir("data-share")
            os.mkdir(os.path.join("data-share", "structure"))
            # Create dummy json obj
            json_obj = {
                "file_list": [self.arbin_file],
                "run_list": [0],
                "validity": ["valid"],
            }
            json_string = json.dumps(json_obj)

            command = "structure {}".format(os_format(json_string))
            result = subprocess.check_call(command, shell=True)
            self.assertEqual(result, 0)
            print(os.listdir(os.path.join("data-share", "structure")))
            processed = loadfn(
                os.path.join(
                    "data-share",
                    "structure",
                    "2017-12-04_4_65C-69per_6C_CH29_structure.json",
                )
            )

        self.assertIsInstance(processed, ProcessedCyclerRun)


class ProcessedCyclerRunTest(unittest.TestCase):
    def setUp(self):
        self.arbin_file = os.path.join(TEST_FILE_DIR, "FastCharge_000000_CH29.csv")
        self.arbin_broken_file = os.path.join(TEST_FILE_DIR, "Talos_001385_NCR18650618003_CH33_truncated.csv")
        self.maccor_file = os.path.join(TEST_FILE_DIR, "xTESLADIAG_000019_CH70.070")
        self.maccor_broken_file = os.path.join(TEST_FILE_DIR, "PreDiag_000229_000229_truncated.034")
        self.neware_file = os.path.join(TEST_FILE_DIR, "raw", "neware_test.csv")

        self.maccor_file_w_diagnostics = os.path.join(
            TEST_FILE_DIR, "xTESLADIAG_000020_CH71.071"
        )
        self.maccor_file_w_parameters = os.path.join(
            TEST_FILE_DIR, "PredictionDiagnostics_000109_tztest.010"
        )
        self.pcycler_run_file = os.path.join(
            TEST_FILE_DIR, "2017-12-04_4_65C-69per_6C_CH29_processed.json"
        )

    def test_from_raw_cycler_run_arbin(self):
        rcycler_run = RawCyclerRun.from_file(self.arbin_file)
        pcycler_run = ProcessedCyclerRun.from_raw_cycler_run(rcycler_run)
        self.assertIsInstance(pcycler_run, ProcessedCyclerRun)
        # Ensure barcode/protocol are passed
        self.assertEqual(pcycler_run.barcode, "EL151000429559")
        self.assertEqual(
            pcycler_run.protocol, r"2017-12-04_tests\20170630-4_65C_69per_6C.sdu"
        )

        all_summary = pcycler_run.summary
        reg_dtypes = all_summary.dtypes.tolist()
        reg_columns = all_summary.columns.tolist()
        reg_dtypes = [str(dtyp) for dtyp in reg_dtypes]
        for indx, col in enumerate(reg_columns):
            self.assertEqual(reg_dtypes[indx], STRUCTURE_DTYPES["summary"][col])

        all_interpolated = pcycler_run.cycles_interpolated
        cycles_interpolated_dyptes = all_interpolated.dtypes.tolist()
        cycles_interpolated_columns = all_interpolated.columns.tolist()
        cycles_interpolated_dyptes = [str(dtyp) for dtyp in cycles_interpolated_dyptes]
        for indx, col in enumerate(cycles_interpolated_columns):
            self.assertEqual(
                cycles_interpolated_dyptes[indx],
                STRUCTURE_DTYPES["cycles_interpolated"][col],
            )

    def test_from_arbin_insufficient_interpolation_length(self):
        os.environ["BEEP_PROCESSING_DIR"] = TEST_FILE_DIR
        rcycler_run = RawCyclerRun.from_file(self.arbin_broken_file)
        vrange, num_points, nominal_capacity, fast_charge, diag = rcycler_run.determine_structuring_parameters()
        print(diag['parameter_set'])
        self.assertEqual(diag['parameter_set'], 'NCR18650-618')
        diag_interp = rcycler_run.get_interpolated_diagnostic_cycles(diag, resolution=1000, v_resolution=0.0005)
        print(diag_interp[diag_interp.cycle_index == 1].charge_capacity.median())
        self.assertEqual(np.around(diag_interp[diag_interp.cycle_index == 1].charge_capacity.median(), 3),
                         np.around(3.428818545441403, 3))

    def test_from_maccor_insufficient_interpolation_length(self):
        os.environ["BEEP_PROCESSING_DIR"] = TEST_FILE_DIR
        rcycler_run = RawCyclerRun.from_file(self.maccor_broken_file)
        vrange, num_points, nominal_capacity, fast_charge, diag = rcycler_run.determine_structuring_parameters()
        print(diag['parameter_set'])
        self.assertEqual(diag['parameter_set'], 'Tesla21700')
        diag_interp = rcycler_run.get_interpolated_diagnostic_cycles(diag, resolution=1000, v_resolution=0.0005)
        self.assertEqual(np.around(diag_interp[diag_interp.cycle_index == 1].charge_capacity.median(), 3),
                         np.around(0.6371558214610992, 3))

    def test_from_raw_cycler_run_maccor(self):
        rcycler_run = RawCyclerRun.from_file(self.maccor_file_w_diagnostics)
        pcycler_run = ProcessedCyclerRun.from_raw_cycler_run(rcycler_run)
        self.assertIsInstance(pcycler_run, ProcessedCyclerRun)
        # Ensure barcode/protocol are passed
        self.assertEqual(pcycler_run.barcode, "EXP")
        self.assertEqual(pcycler_run.protocol, "xTESLADIAG_000020_CH71.000")
        steps = pcycler_run.cycles_interpolated.step_type.unique().tolist()
        # Ensure that charge and discharge steps are processed
        self.assertEqual(steps, ["discharge", "charge"])

        min_index = pcycler_run.cycles_interpolated.cycle_index.min()
        if "step_type" in pcycler_run.cycles_interpolated.columns:
            discharge_interpolated = pcycler_run.cycles_interpolated[
                (pcycler_run.cycles_interpolated.step_type == "discharge")
            ]
            min_index_df = pcycler_run.cycles_interpolated[
                (pcycler_run.cycles_interpolated.cycle_index == min_index)
                & (pcycler_run.cycles_interpolated.step_type == "discharge")
            ]
        else:
            discharge_interpolated = pcycler_run.cycles_interpolated
            min_index_df = pcycler_run.cycles_interpolated[
                (pcycler_run.cycles_interpolated.cycle_index == min_index)
            ]
        matches = discharge_interpolated.groupby("cycle_index").apply(
            lambda x: np.allclose(x.voltage.values, min_index_df.voltage.values)
        )
        if not np.all(matches):
            raise ValueError("cycles_interpolated are not uniform")

    def test_from_raw_cycler_run_neware(self):
        rcycler_run = RawCyclerRun.from_file(self.neware_file)
        pcycler_run = ProcessedCyclerRun.from_raw_cycler_run(rcycler_run)
        self.assertIsInstance(pcycler_run, ProcessedCyclerRun)

    def test_from_raw_cycler_run_parameters(self):
        rcycler_run = RawCyclerRun.from_file(self.maccor_file_w_parameters)
        pcycler_run = ProcessedCyclerRun.from_raw_cycler_run(rcycler_run)
        self.assertIsInstance(pcycler_run, ProcessedCyclerRun)
        # Ensure barcode/protocol are passed
        self.assertEqual(pcycler_run.barcode, "0001BC")
        self.assertEqual(pcycler_run.protocol, "PredictionDiagnostics_000109.000")
        self.assertEqual(pcycler_run.channel_id, 10)

    def test_get_cycle_life(self):
        pcycler_run = loadfn(self.pcycler_run_file)
        self.assertEqual(pcycler_run.get_cycle_life(30, 0.99), 82)
        self.assertEqual(pcycler_run.get_cycle_life(), 189)

    def test_data_types_old_processed(self):
        pcycler_run = loadfn(self.pcycler_run_file)

        all_summary = pcycler_run.summary
        reg_dyptes = all_summary.dtypes.tolist()
        reg_columns = all_summary.columns.tolist()
        reg_dyptes = [str(dtyp) for dtyp in reg_dyptes]
        for indx, col in enumerate(reg_columns):
            self.assertEqual(reg_dyptes[indx], STRUCTURE_DTYPES["summary"][col])

        all_interpolated = pcycler_run.cycles_interpolated
        cycles_interpolated_dyptes = all_interpolated.dtypes.tolist()
        cycles_interpolated_columns = all_interpolated.columns.tolist()
        cycles_interpolated_dyptes = [str(dtyp) for dtyp in cycles_interpolated_dyptes]
        for indx, col in enumerate(cycles_interpolated_columns):
            self.assertEqual(
                cycles_interpolated_dyptes[indx],
                STRUCTURE_DTYPES["cycles_interpolated"][col],
            )

    def test_cycles_to_reach_set_capacities(self):
        pcycler_run = loadfn(self.pcycler_run_file)
        cycles = pcycler_run.cycles_to_reach_set_capacities()
        self.assertGreaterEqual(cycles.iloc[0, 0], 100)

    def test_capacities_at_set_cycles(self):
        pcycler_run = loadfn(self.pcycler_run_file)
        capacities = pcycler_run.capacities_at_set_cycles()
        self.assertLessEqual(capacities.iloc[0, 0], 1.1)

    def test_to_binary(self):
        pcycler_run = loadfn(self.pcycler_run_file)
        with ScratchDir("."):
            pcycler_run.save_numpy_binary("test")
            loaded = ProcessedCyclerRun.load_numpy_binary("test")

        self.assertTrue(
            np.allclose(
                pcycler_run.summary[pcycler_run.SUMMARY_COLUMN_ORDER].values,
                loaded.summary.values,
            )
        )

        self.assertTrue(
            np.allclose(
                pcycler_run.cycles_interpolated[
                    pcycler_run.CYCLES_INTERPOLATED_COLUMN_ORDER
                ].values,
                loaded.cycles_interpolated.values,
            )
        )

        for attribute in pcycler_run.METADATA_ATTRIBUTE_ORDER:
            self.assertEqual(
                getattr(pcycler_run, attribute), getattr(loaded, attribute)
            )

    def test_json_processing(self):

        with ScratchDir("."):
            os.environ["BEEP_PROCESSING_DIR"] = os.getcwd()
            os.mkdir("data-share")
            os.mkdir(os.path.join("data-share", "structure"))

            # Create dummy json obj
            json_obj = {
                "file_list": [self.arbin_file, "garbage_file"],
                "run_list": [0, 1],
                "validity": ["valid", "invalid"],
            }
            json_string = json.dumps(json_obj)
            # Get json output from method
            json_output = process_file_list_from_json(json_string)
            reloaded = json.loads(json_output)

            # Actual tests here
            # Ensure garbage file doesn't have output string
            self.assertEqual(reloaded["invalid_file_list"][0], "garbage_file")

            # Ensure first is correct
            loaded_processed_cycler_run = loadfn(reloaded["file_list"][0])
            loaded_from_raw = RawCyclerRun.from_file(
                json_obj["file_list"][0]
            ).to_processed_cycler_run()
            self.assertTrue(
                np.all(loaded_processed_cycler_run.summary == loaded_from_raw.summary),
                "Loaded processed cycler_run is not equal to that loaded from raw file",
            )

            # Workflow output
            output_file_path = Path(tempfile.gettempdir()) / "results.json"
            self.assertTrue(output_file_path.exists())

            output_json = json.loads(output_file_path.read_text())

            self.assertEqual(reloaded["file_list"][0], output_json["filename"])
            self.assertEqual(os.path.getsize(output_json["filename"]), output_json["size"])
            self.assertEqual(0, output_json["run_id"])
            self.assertEqual("structuring", output_json["action"])
            self.assertEqual("success", output_json["status"])

        # Test same functionality with json file
        with ScratchDir("."):
            os.environ["BEEP_PROCESSING_DIR"] = os.getcwd()
            os.mkdir("data-share")
            os.mkdir(os.path.join("data-share", "structure"))

            json_obj = {
                "file_list": [self.arbin_file, "garbage_file"],
                "run_list": [0, 1],
                "validity": ["valid", "invalid"],
            }
            dumpfn(json_obj, "test.json")
            # Get json output from method
            json_output = process_file_list_from_json("test.json")
            reloaded = json.loads(json_output)

            # Actual tests here
            # Ensure garbage file doesn't have output string
            self.assertEqual(reloaded["invalid_file_list"][0], "garbage_file")

            # Ensure first is correct
            loaded_processed_cycler_run = loadfn(reloaded["file_list"][0])
            loaded_from_raw = RawCyclerRun.from_file(
                json_obj["file_list"][0]
            ).to_processed_cycler_run()
            self.assertTrue(
                np.all(loaded_processed_cycler_run.summary == loaded_from_raw.summary),
                "Loaded processed cycler_run is not equal to that loaded from raw file",
            )

            # Workflow output
            output_file_path = Path(tempfile.gettempdir()) / "results.json"
            self.assertTrue(output_file_path.exists())

            output_json = json.loads(output_file_path.read_text())

            self.assertEqual(reloaded["file_list"][0], output_json["filename"])
            self.assertEqual(os.path.getsize(output_json["filename"]), output_json["size"])
            self.assertEqual(0, output_json["run_id"])
            self.assertEqual("structuring", output_json["action"])
            self.assertEqual("success", output_json["status"])

    def test_auto_load(self):
        loaded = ProcessedCyclerRun.auto_load(self.arbin_file)
        self.assertIsInstance(loaded, ProcessedCyclerRun)


class EISpectrumTest(unittest.TestCase):
    def setUp(self):
        pass

    def test_from_maccor(self):
        eispectrum = EISpectrum.from_maccor_file(
            os.path.join(TEST_FILE_DIR, "maccor_test_file_4267-66-6519.EDA0001.041")
        )


if __name__ == "__main__":
    unittest.main()
