""" Script to calculate LL for a field in a MODIS image"""

import os
import numpy as np
import h5py

from functools import partial
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

from tqdm import tqdm

from IPython import embed
from ulmo import io as ulmo_io
from ulmo.preproc import utils as pp_utils
from ulmo.preproc import extract


def parser(options=None):
    import argparse
    # Parse
    parser = argparse.ArgumentParser(description='Ulmo MODIS extraction')
    parser.add_argument('--year', type=int, default=2010,
                        help='Data year to parse')
    parser.add_argument('--clear_threshold', type=int, default=95,
                        help='Percent of field required to be clear')
    parser.add_argument('--field_size', type=int, default=128,
                        help='Pixel width/height of field')
    parser.add_argument('--quality_threshold', type=int, default=2,
                        help='Maximum quality value considered')
    parser.add_argument('--nadir_offset', type=int, default=480,
                        help='Maximum pixel offset from satellite nadir')
    parser.add_argument('--temp_lower_bound', type=float, default=-2.,
                        help='Minimum temperature considered')
    parser.add_argument('--temp_upper_bound', type=float, default=33.,
                        help='Maximum temperature considered')
    parser.add_argument('--nrepeat', type=int, default=1,
                        help='Repeats for each good block')
    parser.add_argument('--nmin_patches', type=int, default=2,
                        help='Mininum number of random patches to consider from each file')
    parser.add_argument('--nmax_patches', type=int, default=1000,
                        help='Maximum number of random patches to consider from each file')
    parser.add_argument('--ncores', type=int, help='Number of cores for processing')
    parser.add_argument('--nsub_files', type=int, default=20000, help='Number of files to process at a time')
    parser.add_argument("--debug", default=False, action="store_true", help="Debug?")
    parser.add_argument("--wolverine", default=False, action="store_true", help="Run on Wolverine")
    parser.add_argument("--no_inpaint", default=False, action="store_true", help="Turn off inpainting?")
    args = parser.parse_args()

    if options is None:
        pargs = parser.parse_args()
    else:
        pargs = parser.parse_args(options)
    return pargs


def extract_file(ifile, load_path, field_size=(128,128), nadir_offset=480,
                 CC_max=0.05, qual_thresh=2, temp_bounds = (-2, 33), nrepeat=1,
                 inpaint=True, debug=False):

    filename = os.path.join(load_path, ifile)

    # Load the image
    try:
        sst, qual, latitude, longitude = ulmo_io.load_nc(filename, verbose=False)
    except:
        print("File {} is junk".format(filename))
        return
    if sst is None:
        return

    # Generate the masks
    masks = pp_utils.build_mask(sst, qual, qual_thresh=qual_thresh,
                                temp_bounds=temp_bounds)

    # Restrict to near nadir
    nadir_pix = sst.shape[1] // 2
    lb = nadir_pix - nadir_offset
    ub = nadir_pix + nadir_offset
    sst = sst[:, lb:ub]
    masks = masks[:, lb:ub].astype(np.uint8)

    # Random clear rows, cols
    rows, cols, clear_fracs = extract.clear_grid(masks, field_size[0], 'center',
                                                 CC_max=CC_max, nsgrid_draw=nrepeat)
    if rows is None:
        return

    # Extract
    fields, field_masks = [], []
    metadata = []
    for r, c, clear_frac in zip(rows, cols, clear_fracs):
        # Inpaint?
        field = sst[r:r+field_size[0], c:c+field_size[1]]
        mask = masks[r:r+field_size[0], c:c+field_size[1]]
        if inpaint:
            field, _ = pp_utils.preproc_field(field, mask, only_inpaint=True)
        if field is None:
            continue
        # Append SST and mask
        fields.append(field.astype(np.float32))
        field_masks.append(mask)
        # meta
        row, col = r, c + lb
        lat = latitude[row + field_size[0] // 2, col + field_size[1] // 2]
        lon = longitude[row + field_size[0] // 2, col + field_size[1] // 2]
        metadata.append([ifile, str(row), str(col), str(lat), str(lon), str(clear_frac)])

    del sst, masks

    return np.stack(fields), np.stack(field_masks), np.stack(metadata)

def main(pargs):
    """ Run
    """
    # Filenames
    istr = 'F' if pargs.no_inpaint else 'T'
    #load_path = f'/Volumes/Aqua-1/MODIS/night/night/{pargs.year}'
    load_path = f'/Volumes/Aqua-1/MODIS_R2019/night/{pargs.year}'
    save_path = (f'/Volumes/Aqua-1/MODIS/uri-ai-sst/OOD/Extractions/MODIS_R2019_{pargs.year}'
                 f'_{pargs.clear_threshold}clear_{pargs.field_size}x{pargs.field_size}_inpaint{istr}.h5')
    if pargs.wolverine:
        load_path = f'/home/xavier/Projects/Oceanography/AI/OOD'
        save_path = (f'TST_{pargs.year}'
            f'_{pargs.clear_threshold}clear_{pargs.field_size}x{pargs.field_size}.h5')

    # Setup for preproc
    map_fn = partial(extract_file,
                     load_path=load_path,
                     field_size=(pargs.field_size, pargs.field_size),
                     CC_max=1.-pargs.clear_threshold / 100.,
                     qual_thresh=pargs.quality_threshold,
                     nadir_offset=pargs.nadir_offset,
                     temp_bounds=(pargs.temp_lower_bound, pargs.temp_upper_bound),
                     nrepeat=pargs.nrepeat,
                     inpaint=not pargs.no_inpaint,
                     debug=pargs.debug)

    '''
    if pargs.debug:
        files = [f for f in os.listdir(load_path) if f.endswith('.nc')]
        if not pargs.wolverine:
            files = files[0:100]
        answers = []
        for kk, ifile in enumerate(files):
            answers.append(extract_file(ifile,
                     load_path=load_path,
                     field_size=(pargs.field_size, pargs.field_size),
                     CC_max=1.-pargs.clear_threshold / 100.,
                     qual_thresh=pargs.quality_threshold,
                     nadir_offset=pargs.nadir_offset,
                     temp_bounds=(pargs.temp_lower_bound, pargs.temp_upper_bound),
                     nrepeat=pargs.nrepeat))
            print("kk: {}".format(kk))
        embed(header='123 of extract')
    '''

    if pargs.ncores is None:
        n_cores = multiprocessing.cpu_count()
    else:
        n_cores= pargs.ncores
    print("Using: {} cores".format(n_cores))

    # Limit number of files to 10000
    files = [f for f in os.listdir(load_path) if f.endswith('.nc')]
    if pargs.wolverine:
        files = [f for f in os.listdir(load_path) if f.endswith('.nc')] * 50
    elif pargs.debug:
        #files = files[6000:8000]
        files = files[0:1000]

    nloop = len(files) // pargs.nsub_files + ((len(files) % pargs.nsub_files) > 0)
    print('Processing {} files in {} loops of {}'.format(len(files), nloop, pargs.nsub_files))

    fields, masks, metadata = None, None, None
    for kk in range(nloop):
        i0 = kk*pargs.nsub_files
        i1 = min((kk+1)*pargs.nsub_files, len(files))
        print('Files: {}:{} of {}'.format(i0, i1, len(files)))
        sub_files = files[i0:i1]

        with ProcessPoolExecutor(max_workers=n_cores) as executor:
            chunksize = len(sub_files) // n_cores if len(sub_files) // n_cores > 0 else 1
            answers = list(tqdm(executor.map(map_fn, sub_files,
                                             chunksize=chunksize), total=len(sub_files)))

        # Trim None's
        answers = [f for f in answers if f is not None]
        if fields is None:
            fields = np.concatenate([item[0] for item in answers])
            masks = np.concatenate([item[1] for item in answers])
            metadata = np.concatenate([item[2] for item in answers])
        else:
            fields = np.concatenate([fields]+[item[0] for item in answers], axis=0)
            masks = np.concatenate([masks]+[item[1] for item in answers], axis=0)
            metadata = np.concatenate([metadata]+[item[2] for item in answers], axis=0)
        del answers

    # Write
    columns = ['filename', 'row', 'column', 'latitude', 'longitude', 'clear_fraction']

    with h5py.File(save_path, 'w') as f:
        #f.create_dataset('fields', data=fields.astype(np.float32))
        f.create_dataset('fields', data=fields)
        f.create_dataset('masks', data=masks.astype(np.uint8))
        dset = f.create_dataset('metadata', data=metadata.astype('S'))
        dset.attrs['columns'] = columns
