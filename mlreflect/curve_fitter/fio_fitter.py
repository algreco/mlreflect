import numpy as np

from .base_fitter import BaseFitter, reload_scans
from .results import FitResult, FitResultSeries
from ..models import DefaultTrainedModel
from ..xrrloader import FioLoader, NotReflectivityScanError


class FioFitter(BaseFitter):

    @property
    def file_stem(self):
        return self._file_name

    @reload_scans
    def fit(self, scan_number: int, trim_front: int = None, trim_back: int = None, roi: list = None,
            theta_offset: float = 0.0, dq: float = 0.0, factor: float = 1.0, plot=False, polish=True,
            fraction_bounds=(0.5, 0.5, 0.1), optimize_q=True, n_q_samples=1000, reload=True) -> FitResult:
        """Extract scan from file and predict thin film parameters.

        Args:
            scan_number: Scan number of the scan that is to be fitted.
            trim_front: How many intensity points are cropped from the beginning.
            trim_back: How many intensity points are cropped from the end.
            roi: Alternative region of interest in the raw detector image that will be converted to a
                reflectivity curve. The roi specifications must be a list of integers that specify the pixel
                boundaries in the format ``[left, bottom, right, top]``, e.g. ``roi=[241, 106, 247, 109]``.
                This will override the default roi counter.
            theta_offset: Angular correction that is added before transformation to q space.
            dq: Q-shift that is applied before interpolation of the data to the trained q values. Can sometimes
                improve the results if the total reflection edge is not perfectly aligned.
            factor: Multiplicative factor that is applied to the data after interpolation. Can sometimes
                improve the results if the total reflection edge is not perfectly aligned.
            plot: If set to ``True``, the intensity prediction is shown in a plot.
            polish: If ``True``, the predictions will be refined with a simple least log mean squares minimization via
                ``scipy.optimize.minimize``. This can often improve the "fit" of the model curve to the data at the
                expense of higher prediction times.
            fraction_bounds: The relative fitting bounds if the LMS for thickness, roughness and SLD, respectively.
                E.g. if the predicted thickness was 150 A, then a value of 0.5 would mean the fit bounds are
                ``(75, 225)``.
            optimize_q: If ``True``, the q interpolation will be resampled with small q shifts in a range of about
                +-0.003 1/A and the neural network prediction with the smallest MSE will be selected. If
                ``polish=True``, this step will happen before the LMS fit.
            n_q_samples: Number of q shift samples that will be generated. More samples can lead to a better result,
                but will increase the prediction time.
            reload: Decide whether or not to reload all scans in the directory before extracting the data for the fit
                (default ``True``). Depending on the number of scans, this can take some time.

        Returns:
            :class:`FitResult`: An object that contains the fit results as well as useful methods to plot and save
                the results.
        """

        try:
            try:
                scan = self._loader.load_scan(scan_number=scan_number, trim_front=trim_front, trim_back=trim_back,
                                              roi=roi)
            except NotReflectivityScanError as e:
                print(e)
                return
        except (KeyError, FileNotFoundError) as e:
            print(f'scan {scan_number} could not be found in {self._file_name} ({e})')
            return
        scan.scattering_angle += theta_offset
        fit_output = self._curve_fitter.fit_curve(corrected_curve=scan.corrected_intensity, q_values=scan.q, dq=dq,
                                                  factor=factor, polish=polish, fraction_bounds=fraction_bounds,
                                                  optimize_q=optimize_q, n_q_samples=n_q_samples)

        predicted_refl = fit_output['predicted_reflectivity'][0]
        predicted_parameters = fit_output['predicted_parameters']
        best_q_shift = fit_output['best_q_shift'][0]

        fit_result = FitResult(scan_number=scan.scan_number,
                               timestamp=scan.timestamp,
                               corrected_reflectivity=scan.corrected_intensity,
                               q_values_input=scan.q,
                               predicted_reflectivity=predicted_refl,
                               q_values_prediction=self._trained_model.q_values - dq,
                               predicted_parameters=predicted_parameters,
                               best_q_shift=best_q_shift,
                               sample=self._trained_model.sample)
        if plot:
            parameters = [self.trained_model.sample.layers[-1].name + param for param in ('_thickness', '_roughness',
                                                                                          '_sld')]
            fit_result.plot_prediction(parameters)
            fit_result.plot_sld_profile()
        return fit_result

    @reload_scans
    def fit_range(self, scan_range: range, trim_front: int = None, trim_back: int = None, roi: list = None,
                  theta_offset: float = 0.0, dq: float = 0.0, factor: float = 1.0, plot=False, polish=True,
                  fraction_bounds=(0.5, 0.5, 0.1), optimize_q=True, n_q_samples=1000, reload=True) -> FitResultSeries:
        """Iterate fit method over a range of scans."""

        fit_results = []
        for i in scan_range:
            result = self.fit(i, trim_front=trim_front, trim_back=trim_back, roi=roi, theta_offset=theta_offset, dq=dq,
                              factor=factor, plot=False, polish=polish, fraction_bounds=fraction_bounds,
                              optimize_q=optimize_q, n_q_samples=n_q_samples, reload=False)
            if result is not None:
                fit_results.append(result)

        fit_result_series = FitResultSeries(fit_results)

        if plot:
            fit_result_series.plot_sld_profiles()
            parameters = [self.trained_model.sample.layers[-1].name + param for param in ('_thickness', '_roughness',
                                                                                          '_sld')]
            fit_result_series.plot_predicted_parameter_range(parameters)

        return fit_result_series

    @reload_scans
    def show_scans(self, min_scan: int = None, max_scan: int = None, reload=True):
        """Show information about all scans from ``min_scan`` to ``max_scan``."""

        scan_info = self._loader.parser.scan_info
        if max_scan is None:
            max_scan = np.max(np.asarray(list(scan_info.keys()), dtype=int))
        else:
            max_scan = np.min((max_scan, np.max(np.asarray(list(scan_info.keys()), dtype=int))))
        if min_scan is None:
            min_scan = np.min(np.asarray(list(scan_info.keys()), dtype=int))
        else:
            min_scan = np.max((min_scan, np.min(np.asarray(list(scan_info.keys()), dtype=int))))
        for i in range(min_scan, max_scan + 1):
            try:
                out = f'scan #{i}\n' \
                      f'\tcommand: {scan_info[i]["header"]["scan_cmd"]}\n' \
                      f'\tis_theta2theta_scan: {scan_info[i]["is_theta2theta_scan"]}'
                print(out)
            except KeyError:
                print(f'scan #{i}\n\tnot found')

    def set_file(self, file_stem: str):
        self._loader = FioLoader(file_stem, **self._import_params, **self._footprint_params)
        self._file_name = file_stem

    def set_import_params(self, two_theta_counter='tt', default_roi_name='p100k',
                          attenuator_counter='atten_position',
                          division_counter: str = None):
        """Set the parameters necessary to correctly import the scans from the file.

        Args:
            two_theta_counter: Name of the counter that contains half the scattering angle (default: ``'om'``).
            default_roi_name: Counter name of the default region of interest that is extracted as reflectivity (default:
                ``'p100k'``).
            attenuator_counter: Counter of the applied attenuator used to correct possible kinks in the data.
            division_counter: Optional counter that is used to divide the intensity counter by.
        """
        params = {
            'two_theta_counter': two_theta_counter,
            'default_roi_name': default_roi_name,
            'attenuator_counter': attenuator_counter,
            'division_counter': division_counter
        }
        self._import_params.update(params)

    def set_footprint_params(self, sample_length: float, beam_width: float, beam_shape: str = 'gauss',
                             normalize_to: str = 'max'):
        """Set the parameters necessary to apply footprint correction.

        Args:
            sample_length: Sample length along the beam direction in mm.
            beam_width: Beam width along the beam direction (height). For a gaussian beam profile this is the full
                width at half maximum.
            beam_shape:
                ``'gauss'`` (default) for a gaussian beam profile
                ``'box'`` for a box profile
            normalize_to:
                ``'max'`` (default): normalize data by the highest intensity value
                ``'first'``: normalize data by the first intensity value
        """

        params = {
            'beam_width': beam_width,
            'sample_length': sample_length,
            'beam_shape': beam_shape,
            'normalize_to': normalize_to
        }

        self._footprint_params.update(params)

    def _reload_loader(self):
        self._loader = FioLoader(self._file_name, **self._import_params, **self._footprint_params)


class DefaultFioFitter(FioFitter):
    """:class:`FioFitter` that is initialized with a pre-trained model for reflectivity on single-layer systems on
        Si/SiOx."""

    def __init__(self):
        super().__init__()
        self.set_trained_model(DefaultTrainedModel())
