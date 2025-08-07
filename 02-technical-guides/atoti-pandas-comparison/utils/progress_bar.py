# Define a function to print a progress bar
def print_progress_bar(iteration, total, prefix="", suffix="", length=50, fill="█"):
    percent = f"{100 * (iteration / float(total)):.1f}"
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + "-" * (length - filled_length)
    print(f"\r{prefix} |{bar}| {percent}% {suffix}", end="\r")
