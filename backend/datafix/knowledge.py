"""Static domain knowledge: placeholder tokens, aliases, GST state codes."""

DISGUISED_TOKENS = {
    "na", "n/a", "n.a.", "nan", "null", "none", "nil", "-", "--", "---", "?", "??", "unknown", "not available",
    "not applicable", "missing", "tbd", "xxx", "xx", "x", ".", "0000000000", "9999999999", "1234567890",
    "000000", "999999", "123456", "test@test.com", "abc@xyz.com", "test@example.com", "noemail@gmail.com",
    "na@na.com", "1900-01-01", "01/01/1900", "01-01-1900", "1970-01-01", "01/01/1970", "00/00/0000",
}

# normalised alias -> canonical display form
CITY_ALIASES = {
    "bombay": "Mumbai", "bangalore": "Bengaluru", "madras": "Chennai", "calcutta": "Kolkata",
    "gurgaon": "Gurugram", "poona": "Pune", "trivandrum": "Thiruvananthapuram", "cochin": "Kochi",
    "mysore": "Mysuru", "baroda": "Vadodara", "benares": "Varanasi", "banaras": "Varanasi",
    "allahabad": "Prayagraj", "pondicherry": "Puducherry", "simla": "Shimla", "vizag": "Visakhapatnam",
    "mangalore": "Mangaluru", "belgaum": "Belagavi", "hubli": "Hubballi", "calicut": "Kozhikode",
    "trichy": "Tiruchirappalli", "orissa": "Odisha", "uttaranchal": "Uttarakhand", "new bombay": "Navi Mumbai",
}

GST_STATE_CODES = {
    "01": "Jammu And Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat", "26": "Dadra And Nagar Haveli And Daman And Diu",
    "27": "Maharashtra", "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
    "34": "Puducherry", "35": "Andaman And Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh",
    "38": "Ladakh",
}
