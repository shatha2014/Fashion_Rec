#!/usr/bin/env python

"""
Python script for parsing IG-users in JSON formats with spark and
write comments and  captions to CSV or TSV files, one per user

Example commands to run it:

python pre_process_spark.py --input data --format tsv --p --output cleaned
python pre_process_spark.py --input data --format tsv --output cleaned -d
"""

import pyspark
import pyspark.sql
import os
import argparse
import numpy as np
import shutil


def sparkConf():
    "Setup spark configuration, change this to run on cluster"
    conf = pyspark.SparkConf()
    return conf \
        .setMaster("local") \
        .setAppName("fashion_rec_data_setup") \
        .set("spark.hadoop.validateOutputSpecs", "false")


def parse_raw(sqlContext, input, user):
    """Parses the raw json for a user"""
    df = sqlContext.read.json(input + "/" + user + "/" + user + ".json", multiLine=True)
    return df


def mapRow(row):
    """Mapper to convert json row into a row with only comments and caption in string formats"""
    commentsRow = row.comments
    captionRow = row.caption
    comments = commentsRow.data  # select comments
    textComments = " ".join([x.text for x in comments])  # remove metadata from comments
    if hasattr(captionRow, "edges"):
        captions = captionRow.edges
        textCaptions = " ".join([x.node.text for x in captions])
    if hasattr(captionRow, "text"):
        textCaptions = captionRow.text
    if not row.tags is None:
        tags = " ".join([x for x in row.tags])
    else:
        tags = ""
    textComments = textComments.replace("\n", " ")
    textComments = textComments.replace("\t", " ")
    textComments = textComments.replace(",", " ")
    textCaptions = textCaptions.replace("\n", " ")
    textCaptions = textCaptions.replace("\t", " ")
    textCaptions = textCaptions.replace(",", " ")
    tags = tags.replace("\n", " ")
    tags = tags.replace("\t", " ")
    tags = tags.replace(",", " ")
    id = row.urls[0]
    return pyspark.sql.Row(comments=textComments, caption=textCaptions, tags=tags, id=id)


def parse_args():
    """Parses the commandline arguments with argparse"""
    parser = argparse.ArgumentParser(description='Parse flags to configure the json parsing')
    parser.add_argument("-f", "--format", help="output format: (csv|tsv|json)", choices=["csv", "tsv", "json"],
                        default="tsv")
    parser.add_argument("-p", "--parallelized", help="save output in parallelized or single file format",
                        action="store_true")
    parser.add_argument("-i", "--input", help="folder where input documents are", default="data")
    parser.add_argument("-o", "--output", help="folder where output documents are", default="cleaned")
    parser.add_argument("-d", "--documentformat", help="combine all features into a single text per post",
                        action="store_true")
    args = parser.parse_args()
    return args


def writeToFile(rdd, parallelized, output, user, format):
    """Writes the processed RDD to output file"""
    fileEnd = "." + format
    output_path = output + "/" + user + "/" + user + fileEnd
    if parallelized:
        rdd.saveAsTextFile(output_path)
    else:
        arr = np.array(rdd.collect())
        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))
        with open(output_path, 'w+') as tsvfile:
            for row in arr:
                if format == "json":
                    tsvfile.write(row.encode("utf-8", errors='ignore') + "\n")
                else:
                    tsvfile.write(row + "\n")


def format(df, format, features):
    """Formats the RDD pre-output"""

    def mapDocFormat(row):
        if format == "csv":
            return row.id.encode("utf-8", errors='ignore') + "," + " ".join(
                [x.encode("utf-8", errors='ignore') for x in [row.comments, row.caption, row.tags]])
        if format == "tsv":
            return row.id.encode("utf-8") + "\t" + " ".join(
                [x.encode("utf-8", errors='ignore') for x in [row.comments, row.caption, row.tags]])
        if format == "json":
            return pyspark.sql.Row(doc=row.id.encode("utf-8", errors='ignore'), text=''.join([x.encode("utf-8", errors='ignore') for x in row]))

    if features:
        df = df.rdd.map(mapDocFormat)
        if format == "json":
            return df.toDF().toJSON()
        else:
            return df
    else:
        if format == "csv":
            return df.rdd.map(lambda row: ','.join([x.encode("utf-8", errors='ignore') for x in [row.id, row.comments, row.caption, row.tags]]))
        if format == "tsv":
            return df.rdd.map(lambda row: '\t'.join([x.encode("utf-8", errors='ignore') for x in [row.id, row.comments, row.caption, row.tags]]))
        if format == "json":
            return df.toJSON()


def select(df):
    """Selects the columns from the raw JSON RDD"""
    commentsCols = ["comments"]
    captionCols = ["edge_media_to_caption", "caption"]
    tagsCols = ["tags"]
    idCol = "id"
    urlsCol = "urls"
    commentCol = filter(lambda commentCol: commentCol in df.columns, commentsCols)[0]
    captionCol = filter(lambda captionCol: captionCol in df.columns, captionCols)[0]
    tagCol = filter(lambda tagCol: tagCol in df.columns, tagsCols)[0]
    df = df.select([commentCol, captionCol, tagCol, idCol, urlsCol])
    df = df.selectExpr(commentCol + " as comments", captionCol + " as caption", tagCol + " as tags", idCol + " as id", urlsCol + " as urls")
    return df


def parseUser(user, args, sql):
    """Parses a single user JSON file and writes it as CSV or TSV"""
    print "parsing user {}".format(user)
    df = parse_raw(sql, args.input, user)
    df = select(df)
    df = df.rdd.map(lambda x: mapRow(x)).toDF()
    df = format(df, args.format, args.documentformat)
    writeToFile(df, args.parallelized, args.output, user, args.format)


def cleanOutputDir(output):
    """Cleans the output directory to make room for new outputs"""
    if os.path.exists(output) and os.path.isdir(output):
        shutil.rmtree(output)


def main():
    """
    Main function, orchestrates the pipeline.
    Creates the spark context, parses arguments, and parses all users.
    """
    sc = pyspark.SparkContext(conf=sparkConf())
    sql = pyspark.SQLContext(sc)
    args = parse_args()
    cleanOutputDir(args.output)
    users = os.listdir(args.input)
    map(lambda user: parseUser(user, args, sql), users)


if __name__ == '__main__':
    main()