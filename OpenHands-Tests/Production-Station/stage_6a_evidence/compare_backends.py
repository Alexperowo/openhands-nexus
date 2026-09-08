import os

p1 = r"K:\Project\llama.cpp"
p2 = r"K:\Project\llama-mainline\b10816"

files1 = set(os.listdir(p1))
files2 = set(os.listdir(p2))

only1 = files1 - files2
only2 = files2 - files1
common = files1 & files2

print("In llama.cpp only:", only1)
print("In llama-mainline/b10816 only:", only2)
print("Common files count:", len(common))

same_size = []
diff_size = []
for f in common:
    s1 = os.path.getsize(os.path.join(p1, f))
    s2 = os.path.getsize(os.path.join(p2, f))
    if s1 == s2:
        same_size.append(f)
    else:
        diff_size.append((f, s1, s2))

print(f"Same size count: {len(same_size)}, Different size count: {len(diff_size)}")
if diff_size:
    print("Different sizes:", diff_size)
