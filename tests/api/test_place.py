"""Short "City, Country" places for job cards.

Every location string is a real one from the jobs table.
"""

import pytest

from app.api.place import Place, place


@pytest.mark.parametrize(
    ("location", "codes", "expected"),
    [
        # City first, country last
        ("Ratingen, Nordrhein-Westfalen, Germany", ["DE"], "Ratingen, Germany"),
        ("Markham, Ontario, Canada", ["CA"], "Markham, Canada"),
        ("Bengaluru, Karnataka, India", ["IN"], "Bengaluru, India"),
        ("Guangzhou, Guangdong, China", ["CN"], "Guangzhou, China"),
        ("Galway, Ireland", ["IE"], "Galway, Ireland"),
        ("San Jose, California, US", ["US"], "San Jose, USA"),
        ("Amsterdam Drenthe, North Holland, Netherlands", ["NL"], "Amsterdam Drenthe, Netherlands"),
        # Country first, city last (Microsoft, Intel, NVIDIA)
        ("Finland, Satakunta, Tampere", ["FI"], "Tampere, Finland"),
        ("United States, Washington, Redmond", ["US"], "Redmond, USA"),
        ("US, California, Folsom", ["US"], "Folsom, USA"),
        ("Taiwan, Taipei", ["TW"], "Taipei, Taiwan"),
        ("PRC, Shanghai", ["CN"], "Shanghai, China"),
        ("Ireland, Dublin, Dublin", ["IE"], "Dublin, Ireland"),
        ("United States, New York, New York", ["US"], "New York, USA"),
        # Code - City, Country (Visa)
        ("ES - Madrid, Spain", ["ES"], "Madrid, Spain"),
        ("SG - Singapore", ["SG"], "Singapore"),
        # No country in the text: the job's country code fills it in
        ("California - San Francisco", ["US"], "San Francisco, USA"),
        ("O'Fallon, Missouri", ["US"], "O'Fallon, USA"),
        ("Budapest, Millennium Gardens", ["HU"], "Budapest, Hungary"),
        ("Wien - Donau-City-Straße 7", ["AT"], "Wien, Austria"),
        ("Cairo - ETIC", ["EG"], "Cairo, Egypt"),
        ("Bucharest", ["RO"], "Bucharest, Romania"),
        ("United Kingdom - London", ["GB"], "London, UK"),
        # More than one part names a country; the last one is the country
        ("Jamaica, NY, United States", ["JM", "US"], "Jamaica, USA"),
        ("Singapore, Singapore", ["SG"], "Singapore"),
        ("Hong Kong, Hong Kong", ["HK"], "Hong Kong"),
        # State codes and street addresses
        ("Abilene, TX, United States", ["US"], "Abilene, USA"),
        ("6555 Excellence Way, Plano, TX, USA", ["US"], "Plano, USA"),
        ("MI, United States", ["US"], "USA"),
        # Office codes (Broadcom), capitals, notes
        ("IND-Bangalore Electronic City - S1", ["IN"], "Bangalore Electronic City, India"),
        ("CAN-Ontario Remote Location", ["CA"], "Ontario, Canada"),
        ("USA-CA - Promontory B", ["US"], "Promontory B, USA"),
        ("USA-CA-Remote Location", ["US"], "USA"),
        ("BOURNEMOUTH, DORSET, United Kingdom", ["GB"], "Bournemouth, UK"),
        ("(do not use) Mumbai Nirlon Kn. Pk B1", ["IN"], "Mumbai Nirlon Kn. Pk B1, India"),
        # Nothing to go on
        ("Belen", [], "Belen"),
        ("3 Locations", [], "3 Locations"),
    ],
)
def test_city_and_country(location, codes, expected):
    assert place([location], codes, None).text == expected


def test_a_us_state_is_not_read_as_a_country():
    # "Georgia" is also a country, and "IN" is also Indiana; only the job's own codes count.
    assert place(["Atlanta, Georgia, US"], ["US"], None).text == "Atlanta, USA"
    assert place(["Indianapolis, IN"], ["US"], None).text == "Indianapolis, USA"


def test_flag_country_is_the_first_locations_country():
    p = place(["Remote - Germany", "Remote - France"], ["DE", "FR"], None)
    assert (p.text, p.country, p.more) == ("Germany", "DE", 1)


def test_more_counts_the_other_locations():
    p = place(["San Jose", "College Park", "San Francisco", "Seattle"], ["US"], None)
    assert (p.text, p.country, p.more) == ("San Jose, USA", "US", 3)


def test_india_and_remote_marks():
    assert place(["Bengaluru, Karnataka, India", "Galway, Ireland"], ["IE", "IN"], None).india
    assert not place(["Galway, Ireland"], ["IE"], None).india
    assert place(["Remote - Germany"], ["DE"], None).remote
    assert place(["Pune"], ["IN"], "remote").remote
    assert not place(["Pune"], ["IN"], "onsite").remote
    assert not place(["Remoteville, Texas"], ["US"], None).remote
    assert place(["USA-CA-Remote Location"], ["US"], None).remote
    assert place(["San Francisco Bay Remote"], ["US"], None).remote


def test_no_locations():
    india = Place(text="India", country="IN", more=0, india=True, remote=False)
    assert place([], ["IN"], None) == india
    assert place([], [], None) == Place(text="", country=None, more=0, india=False, remote=False)
