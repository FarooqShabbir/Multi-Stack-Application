# AWS's own Lambda base images (public.ecr.aws/lambda/python) are built
# on Amazon Linux -- the SAME OS Lambda actually runs on -- so pip
# installing psycopg2-binary here produces binaries that are guaranteed
# compatible, unlike zipping up a layer built on your own laptop's OS.
# This is the officially recommended approach per AWS's own
# prescriptive guidance for using psycopg2 in Lambda.
FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}
RUN pip install -r requirements.txt

COPY handler.py ${LAMBDA_TASK_ROOT}

CMD ["handler.lambda_handler"]
