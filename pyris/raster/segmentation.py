from __future__ import division
import os, sys
import numpy as np
from skimage.filter import threshold_otsu, rank
from skimage import morphology as mm
from skimage.util import img_as_ubyte


def Thresholding( rgb, band=None ):
    '''Thresholding(rgb) - Apply Otsu's Thresholding Method'''
    # Assign band
    if band is None: idx = 0 # Defaut band is R
    elif isinstance(band, str):
        if band.lower()[0] == 'r': idx = 0
        elif band.lower()[0] == 'g': idx = 1
        elif band.lower()[0] == 'b': idx = 2
    # Apply Threshold to selected Band
    img = rgb[:,:,idx] # Band Index
    thresh = threshold_otsu( img ) # Compute Otsu's Threshold
    bw = img < thresh # Apply Threshold
    return bw


def SegmentationIndex( *args, **kwargs ):
    '''Apply Index'''
    R = kwargs['R'].astype( float )
    G = kwargs['G'].astype( float )
    B = kwargs['B'].astype( float )
    NIR = kwargs.pop( 'NIR', np.full(R.shape,np.nan) ).astype( float )
    MIR = kwargs.pop( 'MIR', np.full(R.shape,np.nan) ).astype( float )
    Bawei = kwargs.pop( 'Bawei', np.full(R.shape,np.nan) ).astype( float )
    index = kwargs.pop( 'index', None )
    rad = kwargs.pop( 'radius', 20 )
    method = kwargs.pop( 'method', 'local' )

    if index == 'NDVI':
        IDX =  (NIR - R) / (NIR + R)
    elif index == 'MNDWI':
        IDX =  (G - MIR) / (G + MIR)
    elif index == 'AWEI':
        raise NotImplementedError
        IDX =  4 * ( G - MIR ) - ( 0.25*NIR + 2.75*Bawei ) # TODO: verify
    else:
        err = 'Index %s not recognized' % IDX
        raise ValueError, err
    
    # Apply Local Otsu's Method
    globthresh = threshold_otsu( IDX[np.isfinite(IDX)] )
    if method == 'local':
        print "applying local Otsu method - this may require some time... \r", 
        selem = mm.disk( rad )
        thresh = rank.otsu( img_as_ubyte(IDX), selem )
        print 'done'
    else:
        thresh = globthresh
    if index == 'NDVI': MASK = img_as_ubyte(IDX) <= thresh
    else: MASK = img_as_ubyte(IDX) >= thresh

    return IDX, MASK.astype( int ), globthresh


