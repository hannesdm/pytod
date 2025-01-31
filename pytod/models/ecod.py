# -*- coding: utf-8 -*-
"""k-Nearest Neighbors Detector (kNN)
"""
# Author: Yue Zhao <zhaoy@cmu.edu>
# License: BSD 2 clause

import numpy as np
import torch

from .base import BaseDetector
from .basic_operators import ecdf_multiple


class ECOD(BaseDetector):
    """ECOD class for Unsupervised Outlier Detection Using Empirical
    Cumulative Distribution Functions (ECOD)
    ECOD is a parameter-free, highly interpretable outlier detection algorithm
    based on empirical CDF functions.
    See :cite:`Li2021ecod` for details.

    Parameters
    ----------
    contamination : float in (0., 0.5), optional (default=0.1)
        The amount of contamination of the data set, i.e.
        the proportion of outliers in the data set. Used when fitting to
        define the threshold on the decision function.


    Attributes
    ----------
    decision_scores_ : numpy array of shape (n_samples,)
        The outlier scores of the training data.
        The higher, the more abnormal. Outliers tend to have higher
        scores. This value is available once the detector is
        fitted.
    threshold_ : float
        The threshold is based on ``contamination``. It is the
        ``n_samples * contamination`` most abnormal samples in
        ``decision_scores_``. The threshold is calculated for generating
        binary outlier labels.
    labels_ : int, either 0 or 1
        The binary labels of the training data. 0 stands for inliers
        and 1 for outliers/anomalies. It is generated by applying
        ``threshold_`` on ``decision_scores_``.
    """

    def __init__(self, contamination=0.1, n_neighbors=5, batch_size=None,
                 device='cuda:0'):
        super(ECOD, self).__init__(contamination=contamination)
        self.n_neighbors = n_neighbors
        self.device = device

    def fit(self, X, y=None, return_time=False):
        """Fit detector. y is ignored in unsupervised methods.

        Parameters
        ----------
        X : numpy array of shape (n_samples, n_features)
            The input samples.

        y : Ignored
            Not used, present for API consistency by convention.

        return_time : boolean (default=True)
            If True, set self.gpu_time to the measured GPU time.

        Returns
        -------
        self : object
            Fitted estimator.
        """
        # todo: add one for pytorch tensor
        # X = check_array(X)
        self._set_n_classes(y)

        if self.device != 'cpu' and return_time:
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()

        # density estimation via ECDF
        self.U_l = ecdf_multiple(X, device=self.device)
        self.U_r = ecdf_multiple(-X, device=self.device)

        if self.device != 'cpu' and return_time:
            end.record()
            torch.cuda.synchronize()

        # take the negative log
        self.U_l = -1 * torch.log(self.U_l)
        self.U_r = -1 * torch.log(self.U_r)

        # aggregate and generate outlier scores
        self.O = torch.maximum(self.U_l, self.U_r)
        self.decision_scores_ = torch.sum(self.O, dim=1).cpu().numpy() * -1

        self._process_decision_scores()

        # return GPU time in seconds
        if self.device != 'cpu' and return_time:
            self.gpu_time = start.elapsed_time(end) / 1000

        return self

    def decision_function(self, X):
        """Predict raw anomaly score of X using the fitted detector.
         For consistency, outliers are assigned with larger anomaly scores.
        Parameters
        ----------
        X : numpy array of shape (n_samples, n_features)
            The training input samples. Sparse matrices are accepted only
            if they are supported by the base estimator.
        Returns
        -------
        anomaly_scores : numpy array of shape (n_samples,)
            The anomaly score of the input samples.
        """
        # use multi-thread execution
        if hasattr(self, 'X_train'):
            original_size = X.shape[0]
            X = np.concatenate((self.X_train, X), axis=0)

        # return decision_scores_.ravel()
