__all__ = ['apply_savgol_filter',
           'convert',
           'crop_image',
           'hough_transform',
           'icrop_image_basic',
           'image_padding',
           'ines_crop',
           'laplacian_kern',
           'Otsu_tresholding',
           'py2gwyddion',
           'read_electolum_file',
           'sgolay2d',
           'sgolay2d_kernel',]


def read_electolum_file(file, pack=True, crop=True):

    """
    Reads raw files .data generated by the greateyes camera
    
    Args:
        file (Path): absolute path of the binary file
        pack (boolean): if true the F frame are stacked in one image
        crop (boolean): if True the image is cropped
        
    Returns:
        (namedtuple):
           electrolum.imgWidth (integer): number N of rows
           electrolum.imgHeight (integer): number M of columns
           electrolum.numPatterns (integer): number F of frame
           electrolum.image (list of F NxM nparray of floats): list of F images
           
    todo: the info1, info2, info3 fields are not correctly decoded

    """

    # Standard library import
    import struct
    from collections import namedtuple

    # 3rd party imports
    import numpy as np
    
    if not pack & crop:
        print('Warning cannot crops chunks of non stacked image')

    data_struct = namedtuple(
        "PV_electrolum",
        [
            "imgWidth",
            "imgHeight",
            "numPatterns",
            "exptime",
            "info1",
            "info2",
            "info3",
            "image",
        ],
    )
    data = open(file, "rb").read()

    # Header parsing
    fmt = "2i"
    imgWidth, imgHeight = struct.unpack(fmt, data[: struct.calcsize(fmt)])
    pos = struct.calcsize(fmt) + 4
    fmt = "i"
    numPatterns = struct.unpack(fmt, data[pos : pos + struct.calcsize(fmt)])[0]

    pos = 18
    lastPaternIsFractional = struct.unpack(fmt, data[pos : pos + struct.calcsize(fmt)])[
        0
    ]
    if lastPaternIsFractional == 1:
        print("WARNING: the last image will contain overlapping information")

    pos = 50
    exptime = struct.unpack(fmt, data[pos : pos + struct.calcsize(fmt)])[0]

    fmt = "21s"
    pos = 100
    info1 = struct.unpack(fmt, data[pos : pos + struct.calcsize(fmt)])[
        0
    ]  # .decode('utf-8')

    fmt = "51s"
    pos = 130
    info2 = struct.unpack(fmt, data[pos : pos + struct.calcsize(fmt)])[
        0
    ]  # .decode('utf-8')

    fmt = "501s"
    pos = 200
    info3 = struct.unpack(fmt, data[pos : pos + struct.calcsize(fmt)])[
        0
    ]  # .decode('utf-8')

    # Images parsing
    list_images = []
    for numPattern in range(numPatterns):
        fmt = str(imgWidth * imgHeight) + "H"
        pos = 1024 * 4 + numPattern * struct.calcsize(fmt)
        y = struct.unpack(fmt, data[pos : pos + struct.calcsize(fmt)])
        
        y = np.array(y).reshape((imgHeight, imgWidth))
        list_images.append(y)

    if pack:
        list_images = np.array([np.concatenate(tuple(list_images), axis=0)])[0,:,:]
        if crop : list_images = icrop_image_basic(list_images)

    return data_struct(
        imgWidth, imgHeight, numPatterns, exptime, info1, info2, info3, np.array(list_images)
    )


def py2gwyddion(image, file):

    """The function py2gwyddion stores an array as a simple field files Gwyddion
        format(.gsf). For more information see the Gwyddionuser guide §5.13 
        http://gwyddion.net/documentation/user-guide-en/gsf.html
    """
    # Standard library import
    import struct

    # 3rd party imports
    import numpy as np

    imgHeight, imgWidth = np.shape(image)
    a = b"Gwyddion Simple Field 1.0\n"  # magic line
    a += f"XRes = {str(imgWidth)}\n".encode("utf8")
    a += f"YRes = {str(imgHeight)}\n".encode("utf8")
    a += (chr(0) * (4 - len(a) % 4)).encode("utf8")  # Adds the NULL padding
                                                     # accordind to the Gwyddion .gsf format

    z = image.flatten().astype(
        dtype=np.float32
    )  # Gwyddion reads IEEE 32bit single-precision floating point numbers
    a += struct.pack(str(len(z)) + "f", *z)

    with open(file, "wb") as binary_file:
        binary_file.write(a)

def crop_image(file):

    """
    The function crop_image reads, crops and stitches a set of electroluminesence images.
    
    Args:
       file (Path) : absolute path of the electroluminescence image.
       
    Returns:
       
    """
    
    # 3rd party import
    import numpy as np
    from skimage import filters

    SAFETY_WIDTH = 10 # The width of the top image is set to the coputed with - SAFETY_WIDTH
    BORNE_SUP = np.Inf
    N_SIGMA = 5       # Number of RMS used to discriminate outlier
    

    def crop_segment_image(img, mode="top", default_width=0):

        # Standard library import
        from collections import Counter

        get_modale = lambda a: (Counter(a[a != 0])).most_common(1)[0][0]

        shift_left = []  # list of the row image left border indice
        width = []       # list of the row image width
        height = np.shape(img)[0]
        for jj in range(height):  # Sweep the image by rows
            ii = np.nonzero(
                img[jj]
            )[0]  # Finds the left border and the image width
            if len(ii):
                shift_left.append(ii[0])
                width.append(ii[-1] - ii[0] + 1)

            else:  # The row contains only zero value
                shift_left.append(0)
                width.append(0)

        modale_shift_left = get_modale(
            np.array(shift_left)
        )  # Finds the modale value of the left boudary
        if mode == "top":
            modale_width = (
                get_modale(np.array(width)) - SAFETY_WIDTH
            )  # Reduces the width to prevent for
            # further overestimation
        else:  # Fixes the image width to the one of the top layer
            modale_width = default_width

        if (
            mode == "top"
        ):  # Slice the image throwing away the upper row with width < modale_width
            img_crop = img[
                np.where(width >= modale_width)[0][0] : height,
                modale_shift_left : modale_width + modale_shift_left,
            ]

        else:  # Slice the image throwing away the lower row with width < modale_width
            img_crop = img[
                0 : np.where(width >= modale_width)[0][-1],
                modale_shift_left : modale_width + modale_shift_left,
            ]

        return img_crop, modale_width

    electrolum = read_electolum_file(file, pack=False)

    images_crop = []
    list_borne_inf =[]
    nbr_images = len(electrolum.image)
    for index, image in enumerate(electrolum.image):  # [:-1] to Get rid of the last image
        BORNE_INF = filters.threshold_otsu(image) # Otsu threshold is used to discriminate the noise from electolum signal
        list_borne_inf.append(BORNE_INF)
        if index == nbr_images - 1: # get rid of the last image if the image contains only noise
            if(np.abs(np.mean(list_borne_inf) - BORNE_INF) > N_SIGMA * np.sqrt(np.std(list_borne_inf))):break
        image = np.where((image < BORNE_INF) | (image > BORNE_SUP), 0, image)
        if index == 0:  # We process the top image
            image_crop, modale_width_0 = crop_segment_image(image, mode="top")
            images_crop.append(image_crop)
        else:
            image_crop, _ = crop_segment_image(
                image, mode="bottom", default_width=modale_width_0
            ) # We fix the image width to the one of the top image
            images_crop.append(image_crop)

    croped_image = np.concatenate(tuple(images_crop), axis=0)

    return croped_image
    
def laplacian_kern(size,sigma):
    """
    laplacian_kern computes 2D laplacian kernel. 
    See Digital Image Processing R. Gonzales, R. Woods p. 582; https://theailearner.com/2019/05/25/laplacian-of-gaussian-log/ 
    
    Args:
        size (int): the pixel size of the kernel
        sigma (float): the standard deviation
    
    Returns:
        (array): kernel matrix
  
    """
    import numpy as np
    

    mexican_hat = lambda x,y:-1/(np.pi*sigma**4)*(1-(x**2+y**2)/(2*sigma**2))*np.exp(-(x**2+y**2)/(2*sigma**2))

    size = size+1 if size%2==0 else size # Force size to be odd
    
    x = np.linspace(-(c:=size//2), c, size)
    x_1, y_1 = np.meshgrid(x, x)
    kern = mexican_hat(x_1, y_1)
    
    kern = kern - kern.sum()/(size**2) # The kernel coefficients must sum to zero so that the response of
                                       # the mask is zero in areas of constant grey level
    
    return kern
    
def sgolay2d_kernel ( window_size, order):
    
    """
    sgolay2d_kernel computes the kernel of solvay-Golay filter.
    see https://www.uni-muenster.de/imperia/md/content/physik_ct/pdf_intern/07_savitzky_golay_krumm.pdf
    
    Args:
        window_size (int): size of the  squared image patche
        order (int): order of the smoothing polynomial
        
    Return:
       (array): kernel of size window_size*window_size
    """
    import itertools
    
    import numpy as np
    
    set_jacobian_row = lambda x,y: [ x**(k-n) * y**n for k in range(order+1) for n in range(k+1) ]
    
    

    if  window_size % 2 == 0:
        raise ValueError('window_size must be odd')
        
    n_terms = ( order + 1 ) * ( order + 2)  / 2.0 #number of terms in the polynomial expression
    if window_size**2 < n_terms:
        raise ValueError('order is too high for the window size')

    half_size = window_size // 2
 
    ind = np.arange(-half_size, half_size+1)
    
    jacobian_mat = [set_jacobian_row(x[0], x[1]) for x in itertools.product(ind, repeat=2)]
    
    jacobian_pseudo_inverse = np.linalg.pinv(jacobian_mat)
    jacobian_pseudo_inverse = [jacobian_pseudo_inverse[i].reshape(window_size, -1) 
                               for i in range(jacobian_pseudo_inverse.shape[0])]
    return jacobian_pseudo_inverse

 
def image_padding(z,window_size): 
    
    import numpy as np
    
    if  window_size % 2 == 0:
        raise ValueError('window_size must be odd')

    half_size = window_size // 2
    
    # pad input array with appropriate values at the four borders
    new_shape = z.shape[0] + 2*half_size, z.shape[1] + 2*half_size
    Z = np.zeros( (new_shape) )
    # top band
    band = z[0, :]
    Z[:half_size, half_size:-half_size] =  band -  np.abs( np.flipud( z[1:half_size+1, :] ) - band )
    # bottom band
    band = z[-1, :]
    Z[-half_size:, half_size:-half_size] = band  + np.abs( np.flipud( z[-half_size-1:-1, :] )  -band )
    # left band
    band = np.tile( z[:,0].reshape(-1,1), [1,half_size])
    Z[half_size:-half_size, :half_size] = band - np.abs( np.fliplr( z[:, 1:half_size+1] ) - band )
    # right band
    band = np.tile( z[:,-1].reshape(-1,1), [1,half_size] )
    Z[half_size:-half_size, -half_size:] =  band + np.abs( np.fliplr( z[:, -half_size-1:-1] ) - band )
    # central band
    Z[half_size:-half_size, half_size:-half_size] = z

    # top left corner
    band = z[0,0]
    Z[:half_size,:half_size] = band - np.abs( np.flipud(np.fliplr(z[1:half_size+1,1:half_size+1]) ) - band )
    # bottom right corner
    band = z[-1,-1]
    Z[-half_size:,-half_size:] = band + np.abs( np.flipud(np.fliplr(z[-half_size-1:-1,-half_size-1:-1]) ) - band )

    # top right corner
    band = Z[half_size,-half_size:]
    Z[:half_size,-half_size:] = band - np.abs( np.flipud(Z[half_size+1:2*half_size+1,-half_size:]) - band )
    # bottom left corner
    band = Z[-half_size:,half_size].reshape(-1,1)
    Z[-half_size:,:half_size] = band - np.abs( np.fliplr(Z[-half_size:, half_size+1:2*half_size+1]) - band )
    
    return Z 
    
def apply_savgol_filter(Z,jacobian_pseudo_inverse,derivative=None):

    import scipy.signal

    if derivative == None:
        m = jacobian_pseudo_inverse[0]
        return scipy.signal.fftconvolve(Z, m, mode='valid')
    elif derivative == 'col':
        c = jacobian_pseudo_inverse[1]
        return scipy.signal.fftconvolve(Z, -c, mode='valid')
    elif derivative == 'row':
        r = jacobian_pseudo_inverse[2]
        return scipy.signal.fftconvolve(Z, -r, mode='valid')
    elif derivative == 'both':
        c = jacobian_pseudo_inverse[1]
        r = jacobian_pseudo_inverse[2]
        return (scipy.signal.fftconvolve(Z, -r, mode='valid'),
                scipy.signal.fftconvolve(Z, -c, mode='valid'))
                
def sgolay2d (z, window_size=5, order=3, derivative=None):

    jacobian_pseudo_inverse = sgolay2d_kernel( window_size, order)
    z_padded = image_padding(z,window_size)
    z_filtered = apply_savgol_filter(z_padded,jacobian_pseudo_inverse,derivative=derivative)
    
    return z_filtered
    
def ines_crop(image,autocrop_para):

    import cv2
    import numpy as np
    
    im_sg = sgolay2d(np.float32(image),
                     autocrop_para['2D SG window_size'],
                     autocrop_para['2D SG order'],
                     derivative=None)

    array_im_lap = cv2.filter2D(im_sg,
                                -1,
                                laplacian_kern(autocrop_para['laplacian kernel size'],
                                                   autocrop_para['laplacian kernel sigma']))

    ind_v = np.where(np.abs(array_im_lap.sum(axis=1)) > 
                     np.std(array_im_lap.sum(axis=1))/autocrop_para['fraction of the std laplacian'])[0]

    ind_h = np.where(np.abs(array_im_lap.sum(axis=0)) > 
                     np.std(array_im_lap.sum(axis=0))/autocrop_para['fraction of the std laplacian'])[0]
    ind_h = ind_h[np.where((ind_h>autocrop_para['ind_h_min'])&(ind_h<autocrop_para['ind_h_max']))[0]]

    array_im_red = image[ind_v.min():ind_v.max(),ind_h.min():ind_h.max()]
    
    return array_im_red
    
def convert(data):

    # 3rd party import
    import numpy as np

    data = data / data.max()  # normalizes data in range 0 - 255
    data = 65535 * data
    return data.astype(np.uint16)

def Otsu_tresholding(im, Ostu_corr=1):
    """Image thresholding using the Otsu's method
    https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=4310076
    
    Args:
        im (ndarray) : image
        
        Ostu_corr (float) : division of the Otsu threshold by Otsu_corr

    Returns:
        im_bin (ndarray) : binarized image
        
    """

    # 3rd party import
    from skimage import filters
    import numpy as np

    thresh_otsu = filters.threshold_otsu(
        convert(im)
    )  # détermination du seuil optimum selon Otsu
    im_bin = np.where((convert(im) < thresh_otsu / Ostu_corr), 1, 0)
    return im_bin  

def crop_image(image,autocrop_para):
    

    import cv2
    import numpy as np
    import scipy

    def limit_crop_x_y(im_bin,axis):
        y = np.array([1 if x >= im_bin.shape[axis]*0.99 else 0 for x in im_bin.sum(axis=axis)])

        max_min =np.where(np.abs(np.diff(y))==1)[0]
        max_min = np.insert(
                max_min,            
                [0,len(max_min)],       
                [0,im_bin.shape[1-axis]]        
            )
        intervals  = list(zip(max_min[0:-1],max_min[1:]))
        idx_min,idx_max = sorted(intervals,key=lambda t: t[1]-t[0])[-1]
        return (idx_min,idx_max)


    im_sg = sgolay2d(np.float32(image),
                     autocrop_para['2D SG window_size'],
                     autocrop_para['2D SG order'],
                     derivative=None)

    array_im_lap = cv2.filter2D(im_sg,
                                -1,
                                laplacian_kern(autocrop_para['laplacian kernel size'],
                                                   autocrop_para['laplacian kernel sigma']))



    im_bin = Otsu_tresholding(array_im_lap,Ostu_corr=1)
    im_bin = scipy.ndimage.median_filter(im_bin,
                                         size=autocrop_para['median_size'],
                                         mode='reflect',)


    idx_x_min,idx_x_max = limit_crop_x_y(im_bin,0)
    idx_y_min,idx_y_max = limit_crop_x_y(im_bin,1)

    image = image[idx_y_min:idx_y_max,idx_x_min:idx_x_max]
    
    return image    

def icrop_image_basic(image):

    import numpy as np
    from skimage import filters
   

    def limit_crop_x_y(axis,im_bin):
        y = image_bin.sum(axis=axis)
        y_not_0 = np.where(y >0)[0]
        idx_min,idx_max = y_not_0[0],y_not_0[-1]
        return (idx_min,idx_max)

    borne_inf = filters.threshold_otsu(image) # Otsu threshold is used to discriminate the noise from electolum signal
    image_bin = np.where((image < borne_inf) , 0, image)

    idx_x_min,idx_x_max = limit_crop_x_y(0,image_bin)
    idx_y_min,idx_y_max = limit_crop_x_y(1,image_bin)

    image_crop = image[idx_y_min:idx_y_max,idx_x_min:idx_x_max]
    
    return image_crop
    
def hough_transform(image):
    
    from skimage.transform.hough_transform import hough_line, hough_line_peaks

    import cv2
    import numpy as np
    import matplotlib.pyplot as plt

    # Construct test image
    autocrop_para = {'2D SG window_size':7,
                     '2D SG order':4,
                     'laplacian kernel size':7,
                     'laplacian kernel sigma':4,
                     }


    array_im_lap = cv2.filter2D(convert(image),
                                -1,
                               laplacian_kern(autocrop_para['laplacian kernel size'],
                                                  autocrop_para['laplacian kernel sigma']))

    array_im_bin = np.where(array_im_lap>3,1,0)



    h, theta, d = hough_line(array_im_bin)

    plt.figure(figsize=(8, 4))

    plt.subplot(131)
    plt.imshow(array_im_bin, cmap=plt.cm.gray)
    plt.title('Input image')

    plt.subplot(132)
    plt.imshow(h,
               #extent=[np.rad2deg(theta[-1]), np.rad2deg(theta[0]),
               #        d[-1], d[0]],
               cmap=plt.cm.gray, aspect=0.05)
    plt.title('Hough transform')
    plt.xlabel('Angles (degrees)')
    plt.ylabel('Distance (pixels)')

    plt.subplot(133)
    plt.imshow(image, cmap=plt.cm.gray)
    rows, cols = image.shape
    for _, angle, dist in zip(*hough_line_peaks(h, theta, d)):
        y0 = (dist - 0 * np.cos(angle)) / np.sin(angle)
        y1 = (dist - cols * np.cos(angle)) / np.sin(angle)
        plt.plot((0, cols), (y0, y1), '-r')
    plt.axis((0, cols, rows, 0))
    plt.title('Detected lines')
    
    _,angle,d = hough_line_peaks(h, theta, d)
    
    return np.rad2deg(angle),d