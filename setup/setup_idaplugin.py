import setup_base

package_data = {'idaplugin/rematch': ['images/*']}
setup_base.build_setup(name='rematch-idaplugin',
                       version_path='idaplugin/rematch',
                       package_base='idaplugin',
                       package_data=package_data)
