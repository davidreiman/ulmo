""" Methods to slurp LLC data of interest"""


def write_sst(xr_da, outfile, strip_coord=True, encode=True):
    """

    Parameters
    ----------
    xr_da : xarray.DataArray
    strip_coord
    encode : bool, optional

    """

    # Strip coords?
    if strip_coord:
        drop_coord = []
        for key in xr_da.coords.keys():
            if key in ['i', 'j']:
                continue
            drop_coord.append(key)
        xr_da = xr_da.drop_vars(drop_coord)

    # Convert to Dataset
    xr_ds = xr_da.to_dataset()

    # Encode?
    if encode:
        encoding = {}
        encoding['Theta'] = {'dtype': 'int16', 'scale_factor': 1e-3,
                             'add_offset': 10., 'zlib': True, 'missing_value': -32768}
    else:
        encoding = None

    # Write
    xr_ds.to_netcdf(outfile, encoding=encoding)