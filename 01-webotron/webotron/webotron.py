#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Webotron: Deploy websites to aws.

Webotron automates the process of deploying static websites to AWS.
- Configure AWS S3 buckets
    - Create them
    - Set them up for static website hosting
    - Deploy local files
- Configure DNS with AWS Route53
- Configure a Content Delivery Network and SSL with AWS CloudFront
"""


import click
import boto3

from webotron.bucket import BucketManager
from webotron.domain import DomainManager
from webotron.cdn import DistributionManager
from webotron.certificate import CertificateManager
from webotron import util

session = None
bucket_manager = None
domain_manager = None
cert_manager = None
dist_manager = None


@click.group()
@click.option('--profile', default=None, help='Use a given AWS Profile.')
def cli(profile):
    """Webotron deploys websites to AWS."""
    global session, bucket_manager, domain_manager, cert_manager, dist_manager

    session_cfg = {}
    if profile:
        session_cfg['profile_name'] = profile

    session = boto3.Session(**session_cfg)
    bucket_manager = BucketManager(session)
    domain_manager = DomainManager(session)
    cert_manager = CertificateManager(session)
    dist_manager = DistributionManager(session)


@cli.command('list-buckets')
def list_buckets():
    """List all s3 buckets."""
    for bucket in bucket_manager.all_buckets():
        print(bucket)


@cli.command('list-bucket-objects')
@click.argument('bucket')
def list_bucket_objects(bucket):
    """List objects in an S3 bucket."""
    for obj in bucket_manager.all_objects(bucket):
        print(obj)


@cli.command('setup-bucket')
@click.argument('bucket')
def setup_bucket(bucket):
    """Create and configure S3 bucket."""
    s3_bucket = bucket_manager.init_bucket(bucket)
    bucket_manager.set_policy(s3_bucket)
    bucket_manager.configure_website(s3_bucket)

    return


@cli.command('sync')
@click.argument('pathname', type=click.Path(exists=True))
@click.argument('bucket')
def sync(pathname, bucket):
    """Sync content of PATHNAME to the BUCKET."""
    bucket_manager.sync(pathname, bucket)
    print(bucket_manager.get_bucket_url(bucket_manager.s3.Bucket(bucket)))


@cli.command('setup-domain')
@click.argument('domain')
def setup_domain(domain):
    """Configure DOMAIN to point to BUCKET."""
    bucket = bucket_manager.get_bucket(domain)

    zone = domain_manager.find_hosted_zone(domain) \
        or domain_manager.create_hosted_zone(domain)

    endpoint = util.get_endpoint(bucket_manager.get_region_name(bucket))
    domain_manager.create_s3_domain_record(zone, domain, endpoint)
    print("Domain configured: http://{}".format(domain))

@cli.command('find-cert')
@click.argument('domain')
def find_cert(domain):
    """Find a certificate for <DOMAIN>."""
    print(cert_manager.find_matching_cert(domain))

@cli.command('setup-cdn')
@click.argument('domain')
@click.argument('bucket')
def setup_cdn(domain, bucket):
    dist = dist_manager.find_matching_dist(domain)

    if not dist:
        cert = cert_manager.find_matching_cert(domain)
        if not cert: # SSL is not optional at this time.
            print("Error: No matching cert found.")
            return

        dist = dist_manager.create_dist(domain, cert)
        print("Waiting for distribution deloyment...")
        dist_manager.await_deploy(dist)

    zone = domain_manager.find_hosted_zone(domain) \
        or domain_manager.create_hosted_zone(domain)

    domain_manager.create_cf_domain_record(zone, domain, dist['DomainName'])
    print("Domain configured: https://{}".format(domain))

    return


if __name__ == '__main__':
    cli()
