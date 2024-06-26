import ROOT


def validate_root_file(fpath: str) -> None:
    """
    Opening the ROOT file and getting the UUID seems to be enough
    to check fi the file is corrupted or not.
    """
    with ROOT.TFile(fpath) as root_file:
        root_file.GetUUID().AsString()
