from __future__ import division
import numpy as np
from scipy import interpolate
from numpy.lib import stride_tricks
from ..misc import GeoReference, Line2D

class AxisReader( object ):
    '''
    Read Pruned and Skeletonized Axis/Distance Image and
    extract vector data.
    '''

    primitives = ([[1,0,0],
                   [0,1,0],
                   [0,0,0]],
                  [[0,1,0],
                   [0,1,0],
                   [0,0,0]])

    def __init__( self, I, first_point=None, start_from=None, method='width', verbose=True, call_depth=0, jidx=[] ):
        '''Constructor'''
        self.I = I
        self.hits = np.where( I>0, 1, 0 ).astype( int )
        self.first_point = first_point # Initial Point if known (used in recursion)
        self.start_from = 'b' if start_from is None else start_from # Where flow comes from
        self.method = method # Method used for multithread reaches
        self.verbose = verbose
        self.call_depth = call_depth # Level of recursion
        self.jidx = jidx # Indexes of multithread junctions
        return None

    def GetJunction( self, idx ):
        '''List of multithread junctions indexes'''
        if len( self.jidx ) > 0: idx += self.jidx[-1]
        self.jidx.append( idx )

    def BuildStrides( self ):
        '''Build cache-friendly Strides Array'''
        n = 3
        i = 1 + self.hits.shape[0] - 3
        j = 1 + self.hits.shape[1] - 3
        return stride_tricks.as_strided( self.hits, (i,j,n,n), strides=2*self.hits.strides )

    def GetFirstPoint( self ):
        '''Look for a 3x3 primitive in the image corresponding to the channel starting point'''

        if self.first_point is not None:
            self.i0, self.j0 = self.first_point
            return None

        strides = self.BuildStrides()

        if self.start_from == 'b':
            for i in xrange( self.hits.shape[0]-1, 0, -1 ):
                if np.all( self.hits[i,:] == 0 ): continue
                for j in xrange( 1, self.hits.shape[1]-1 ):
                    for primitive in self.primitives:
                        for iSide in xrange( 4 ):
                            seed = np.rot90( primitive, iSide )
                            if ( strides[i-1,j-1] == seed ).all():
                                self.i0, self.j0 = i, j
                                return None

        elif self.start_from == 't':
            for i in xrange( 1, self.hits.shape[0] ):
                if np.all( self.hits[i,:] == 0 ): continue
                for j in xrange( 1, self.hits.shape[1]-1 ):
                    if self.hits[i,j] == 0: continue
                    for primitive in self.primitives:
                        for iSide in xrange( 4 ):
                            seed = np.rot90( primitive, iSide )
                            if ( strides[i-1,j-1] == seed ).all():
                                self.i0, self.j0 = i, j
                                return None

        elif self.start_from == 'l':
            for j in xrange( 1, self.hits.shape[1] ):
                if np.all( self.hits[:,j] == 0 ): continue
                for i in xrange( 1, self.hits.shape[0]-1 ):
                    for primitive in self.primitives:
                        for iSide in xrange( 4 ):
                            seed = np.rot90( primitive, iSide )
                            if ( strides[i-1,j-1] == seed ).all():
                                self.i0, self.j0 = i, j
                                return None

        elif self.start_from == 'r':
            for j in xrange( self.hits.shape[1]-1, 0, -1 ):
                if np.all( self.hits[:,j] == 0 ): continue
                for i in xrange( 1, self.hits.shape[0]-1 ):
                    for primitive in self.primitives:
                        for iSide in xrange( 4 ):
                            seed = np.rot90( primitive, iSide )
                            if ( strides[i-1,j-1] == seed ).all():
                                self.i0, self.j0 = i, j
                                return None

        raise IndexError, 'First Point Not Found!'    


    def NeiDist( self, idx1, idx2 ):
        '''Cartesian Distance between pixel cells'''
        i1, j1 = idx1
        i2, j2 = idx2
        return np.sqrt( (i1-i2)**2 + (j1-j2)**2 )


    def Vectorize( self, MAXITER=100000 ):

        '''Find Indexes and Points'''

        I, J = [ self.i0 ], [ self.j0 ] # Lists of channel points
        N = 0 # Counter
        ijunct = 0 # Junction Index

        for ITER in xrange( MAXITER ):
            i0, j0 = I[-1], J[-1] # Previous Point
            self.hits[i0,j0] = 0 # Set it to 0 in the Hit&Miss Matrix
            seed = self.hits[i0-1:i0+2, j0-1:j0+2] # 3x3 neighboring element
            pos = zip( *np.where( seed > 0 ) ) # Positive neighbors

            if len( pos ) == 0: # End Point of the channel found
                break

            elif len( pos ) == 1: # Next Point identified
                i, j = pos[0]
                i += i0 - 1 # Reference system
                j += j0 - 1 # Reference system    
                I.append(i), J.append(j)
                N += 1

            elif len( pos ) > 1: # More neighboring points
                jdist = self.NeiDist( pos[0], pos[1] )
                if len( pos ) == 2 and np.abs(jdist-1) < 1.e-08:
                    # Two Neighboring cells are found
                    # Pattern:
                    #          - * *    o=current cell
                    #          - o -    *=neighboring cells
                    #          - - -    -=0 cells
                    dist = np.zeros( len(pos) )
                    # Choose the closest positive cell
                    for ipos, p in enumerate(pos):
                        dist[ipos] = np.sqrt( (1 - p[0])**2 + (1 - p[1])**2 )
                    idist = dist.argmin()
                    pos = [ pos[idist] ]
                    i, j = pos[0]
                    i += i0 - 1
                    j += j0 - 1
                    I.append(i), J.append(j)
                    N += 1

                else: # Multithread channel junction
                    if self.call_depth==0:
                        print 'channel junction at ', i0, j0, 'n branches %d - ' % len( pos ), \
                            'starting recursion (this may require some time)...'
                    elif self.call_depth > 0 and self.verbose:
                        print 'channel junction at ', i0, j0, 'n branches %d - ' % len( pos ), \
                            'level of recursion: %d' % ( self.call_depth )

                    jncsl = [] # Total Lengths of the Following Branches at Junction
                    jncsw = [] # Average Width of the Following Branches at Junction
                    rdepths = []
                    self.GetJunction( N )                    
                    axijs = []

                    for ij in xrange( len(pos) ):

                        # For each of the Junctions is created a recursive instance
                        first_point = ( pos[ij][0]+i0-1, pos[ij][1]+j0-1 ) # Initial Point of the Local Branch

                         # Temporally remove other branches
                        removed_indexes = [ ij-1, (ij+1)%len(pos) ]
                        for idx in removed_indexes: self.hits[ pos[idx][0]+i0-1, pos[idx][1]+j0-1 ] = 0

                        # Recursive call
                        axr = AxisReader( self.I*self.hits, first_point=first_point, method=self.method,
                                          call_depth=self.call_depth+1, jidx=self.jidx )
                        axij = axr( MAXITER=MAXITER )

                        # Set back the other branches
                        for idx in removed_indexes: self.hits[ pos[idx][0]+i0-1, pos[idx][1]+j0-1 ] = 1

                        # Check whether we are in a closed loop
                        x0, x1, y0, y1 = axij[0][0], axij[0][-1], axij[1][0], axij[1][-1]
                        if len(axij[0])>10 and np.sqrt( (x1-x0)**2 + (y1-y0)**2) < 3: continue
                        
                        axijs.append( axij ) # List of recursive AxisReader instances
                        jncsl.append( axij[2].size ) # Total path length
                        jncsw.append( axij[2].mean() ) # Total path average width
                        rdepths.append(axr.call_depth ) # Total level of recursion

                    jncsl, jncsw, rdepths = map( np.asarray, (jncsl,jncsw,rdepths) )

                    if len(axijs) == 0: break # I could get a Zero sometimes but that's ok (only going backward on bifos)

                    if self.method == 'length':
                        IDX = jncsl.argmax()
                    if self.method == 'width':
                        IDX = jncsw.argmax()
                    elif self.method == 'std':
                        # Length Control
                        try:idx_to_rm = np.where( jncsl<0.75*jncsl.max() )[0]
                        except:
                            from matplotlib import pyplot as plt
                            plt.figure()
                            plt.imshow(self.hits, cmap='spectral', interpolation='none')
                            plt.plot(J[-1], I[-1], 'ro')
                            plt.show()
                            
                        axijs = [ elem for k,elem in enumerate(axijs) if k not in idx_to_rm ]
                        jncsl = np.delete( jncsl, idx_to_rm )
                        jncsw = np.delete( jncsw, idx_to_rm )
                        rdepths = np.delete( rdepths, idx_to_rm )
                        IDX = jncsw.argmax()
                    else:
                        raise ValueError, 'method %s not known. Must be either "std", "length" or "width"' % self.method

                    # Take the Widest between the remaining branches
                    _J, _I, _ = axijs[ IDX ]
                    self.call_depth = rdepths[ IDX ]
                    I.extend( _I ), J.extend( _J )
                    del axijs, axij, axr # Free some Memory
                    break


        if ITER == MAXITER-1 and not self.method == 'fast':
            print 'WARNING: Maximum number of iteration reached in axis extraction!'
        I, J = np.asarray( I ), np.asarray( J )
        B = self.I[I, J]
        return [ J, I, B ]

    def __call__( self, MAXITER=100000 ):
        self.GetFirstPoint()
        return self.Vectorize( MAXITER=MAXITER )

                


def ReadAxisLine( I, flow_from=None, method='std', MAXITER=100000 ):

    '''
    Convenience function for AxisReader class.
    Return a Line2D instance with width as attribute.
    
    Args
    ====
    I : Image array of the channel axis over black background
    Return
    ======
    Line2D with axis coordinates, intrinsic coordinate
    and local width distribution dictionary attributes
    '''
    
    r = AxisReader( I, start_from=flow_from, method=method )
    [ Xpx, Ypx, Bpx ] = r( MAXITER=MAXITER )
    print 'axis read with a recursion level of %s' % r.call_depth
    
    # Pixelled Line
    # -------------
    line = Line2D( x=Xpx, y=Ypx, B=Bpx )
    return line

    ## # GeoReferenced Line
    ## # ------------------
    ## GR = GeoReference( I, GeoTransf )
    ## X, Y = GR.RefCurve( Xpx, Ypx )
    ## B = Bpx * GeoTransf['PixelSize']
    ## geoline = Line2D( [ X, Y ] )
    ## geoline.attr( 'B', B )
    ## dx = np.ediff1d( X, to_begin=0 )
    ## dy = np.ediff1d( Y, to_begin=0 )
    ## ds = np.sqrt( dx**2 + dy**2 )
    ## s = np.cumsum( ds )
    ## geoline.attr( 's', s )
    ## geoline.attr( 'L', line.d['s'][-1] )
    #return line, geoline




