# Set explicit platform (for ARM-based Macbooks)
FROM --platform=linux/amd64 atoti/notebooks:latest AS builder

# Set container executable
CMD [ "make", "render" ]
